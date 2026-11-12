"""Unit and integration tests for PaymentExecutionService."""

from __future__ import annotations

from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from agentbounty.agents.registry import AgentRegistry
from agentbounty.config.settings import Settings
from agentbounty.domain.enums import (
    AuthorizationDecision,
    BountyStatus,
    PaymentExecutionMode,
    PaymentStatus,
    TaskStatus,
)
from agentbounty.exceptions import (
    DuplicatePaymentError,
    EntityNotFoundError,
    InvalidAuthorizationError,
    InvalidStateTransitionError,
    UnauthorizedActorError,
)
from agentbounty.payments.authorization import PaymentAuthorizationService
from agentbounty.payments.execution import PaymentExecutionService
from agentbounty.payments.providers.mock import MockPaymentProvider
from agentbounty.payments.schemas import (
    ActorContext,
    AuthorizationRequest,
    PaymentExecutionRequest,
)
from agentbounty.persistence.models import Bounty, PaymentTransaction, Task
from agentbounty.persistence.repositories import AuditEventRepository
from agentbounty.services.task_orchestration import TaskOrchestrationService


@pytest.fixture
def authorized_workflow(session: Session, test_settings: Settings):
    """Complete workflow through human authorization."""
    registry = AgentRegistry()
    registry.sync_with_db(session)
    orchestrator = TaskOrchestrationService(session=session, registry=registry, settings=test_settings)

    res = orchestrator.run_full_workflow(
        title="Execution Test Task",
        description="Introduction for AgentBounty with detailed sections.",
        acceptance_criteria=["contains:AgentBounty", "min_words:10"],
        created_by="founder_frank",
        proposed_bounty=Decimal("4.50"),
    )

    auth_service = PaymentAuthorizationService(session=session, settings=test_settings)
    auth = auth_service.authorize_payment(
        AuthorizationRequest(
            task_id=res.task.id,
            bounty_id=res.bounty.id,
            authorized_amount=Decimal("4.50"),
            currency="USD",
            decision=AuthorizationDecision.AUTHORIZED,
            actor=ActorContext(actor_type="HUMAN", actor_id="founder_frank"),
            reason="All criteria met.",
        )
    )
    return res, auth


class TestPaymentExecutionService:
    """Test suite for PaymentExecutionService."""

    def test_successful_authorized_payment(
        self, session: Session, test_settings: Settings, authorized_workflow
    ) -> None:
        res, auth = authorized_workflow
        provider = MockPaymentProvider()
        exec_service = PaymentExecutionService(session=session, provider=provider, settings=test_settings)

        actor = ActorContext(actor_type="HUMAN", actor_id="finance_operator")
        req = PaymentExecutionRequest(
            authorization_id=auth.id,
            actor=actor,
        )

        exec_res = exec_service.execute_payment(req)

        # 1. Returned schema validation
        assert exec_res.status == PaymentStatus.SUCCEEDED
        assert exec_res.is_duplicate is False
        assert exec_res.transaction.amount == 450
        assert exec_res.transaction.execution_mode == PaymentExecutionMode.SIMULATED
        assert exec_res.transaction.external_reference is None
        assert exec_res.task.status == TaskStatus.COMPLETED
        assert exec_res.bounty.status == BountyStatus.PAID

        # 2. Database records validation
        db_tx = session.get(PaymentTransaction, exec_res.transaction.id)
        assert db_tx is not None
        assert db_tx.status == PaymentStatus.SUCCEEDED

        db_task = session.get(Task, res.task.id)
        assert db_task.status == TaskStatus.COMPLETED

        db_bounty = session.get(Bounty, res.bounty.id)
        assert db_bounty.status == BountyStatus.PAID

        # 3. Audit trail verification
        audit_repo = AuditEventRepository(session)
        events = [e.event_type for e in audit_repo.list_by_correlation_id(exec_res.correlation_id)]
        assert "PAYMENT_TRANSACTION_CREATED" in events
        assert "PAYMENT_SUBMITTED" in events
        assert "PAYMENT_SUCCEEDED" in events
        assert "TASK_COMPLETED" in events
        assert "BOUNTY_PAID" in events

    def test_missing_authorization_rejected(
        self, session: Session, test_settings: Settings
    ) -> None:
        exec_service = PaymentExecutionService(session=session, settings=test_settings)
        actor = ActorContext(actor_type="HUMAN", actor_id="operator")
        req = PaymentExecutionRequest(
            authorization_id="non-existent-auth-id",
            actor=actor,
        )
        with pytest.raises(EntityNotFoundError, match="PaymentAuthorization with ID '.*' not found"):
            exec_service.execute_payment(req)

    def test_unauthorized_actor_rejected(
        self, session: Session, test_settings: Settings, authorized_workflow
    ) -> None:
        res, auth = authorized_workflow
        exec_service = PaymentExecutionService(session=session, settings=test_settings)
        actor = ActorContext(actor_type="MANAGER", actor_id="manager_agent")
        req = PaymentExecutionRequest(
            authorization_id=auth.id,
            actor=actor,
        )
        with pytest.raises(UnauthorizedActorError, match="Payment execution requires explicit HUMAN"):
            exec_service.execute_payment(req)

    def test_unauthorized_decision_rejected(
        self, session: Session, test_settings: Settings, authorized_workflow
    ) -> None:
        res, auth = authorized_workflow
        # Revoke authorization
        auth_service = PaymentAuthorizationService(session=session, settings=test_settings)
        from agentbounty.payments.schemas import RevocationRequest
        auth_service.revoke_authorization(
            RevocationRequest(
                authorization_id=auth.id,
                actor=ActorContext(actor_type="HUMAN", actor_id="founder_frank"),
                reason="Pausing execution",
            )
        )

        exec_service = PaymentExecutionService(session=session, settings=test_settings)
        req = PaymentExecutionRequest(
            authorization_id=auth.id,
            actor=ActorContext(actor_type="HUMAN", actor_id="operator"),
        )
        with pytest.raises(InvalidAuthorizationError, match="decision is 'REVOKED'"):
            exec_service.execute_payment(req)

    def test_duplicate_execution_returns_existing_transaction(
        self, session: Session, test_settings: Settings, authorized_workflow
    ) -> None:
        res, auth = authorized_workflow
        exec_service = PaymentExecutionService(session=session, settings=test_settings)
        actor = ActorContext(actor_type="HUMAN", actor_id="operator")
        req = PaymentExecutionRequest(authorization_id=auth.id, actor=actor)

        # First execution
        first_res = exec_service.execute_payment(req)
        assert first_res.status == PaymentStatus.SUCCEEDED
        assert first_res.is_duplicate is False

        # Duplicate execution
        second_res = exec_service.execute_payment(req)
        assert second_res.is_duplicate is True
        assert second_res.transaction.id == first_res.transaction.id
        assert second_res.status == PaymentStatus.SUCCEEDED

    def test_provider_timeout_leads_to_unknown_without_blind_retry(
        self, session: Session, test_settings: Settings, authorized_workflow
    ) -> None:
        res, auth = authorized_workflow
        # Provider configured to simulate timeout
        provider = MockPaymentProvider(simulate_timeout=True)
        exec_service = PaymentExecutionService(session=session, provider=provider, settings=test_settings)

        actor = ActorContext(actor_type="HUMAN", actor_id="operator")
        req = PaymentExecutionRequest(authorization_id=auth.id, actor=actor)

        exec_res = exec_service.execute_payment(req)
        assert exec_res.status == PaymentStatus.UNKNOWN
        assert exec_res.transaction.status == PaymentStatus.UNKNOWN

        # Task and Bounty remain in PAYMENT_PENDING
        db_task = session.get(Task, res.task.id)
        db_bounty = session.get(Bounty, res.bounty.id)
        assert db_task.status == TaskStatus.PAYMENT_PENDING
        assert db_bounty.status == BountyStatus.PAYMENT_PENDING

        # Repeated execution must not resubmit; returns existing UNKNOWN transaction
        dup_res = exec_service.execute_payment(req)
        assert dup_res.is_duplicate is True
        assert dup_res.status == PaymentStatus.UNKNOWN

    def test_provider_failure_marks_task_failed_and_keeps_bounty_awarded(
        self, session: Session, test_settings: Settings, authorized_workflow
    ) -> None:
        res, auth = authorized_workflow
        provider = MockPaymentProvider(simulate_failure=True)
        exec_service = PaymentExecutionService(session=session, provider=provider, settings=test_settings)

        actor = ActorContext(actor_type="HUMAN", actor_id="operator")
        req = PaymentExecutionRequest(authorization_id=auth.id, actor=actor)

        exec_res = exec_service.execute_payment(req)
        assert exec_res.status == PaymentStatus.FAILED

        # Task transitions to FAILED
        db_task = session.get(Task, res.task.id)
        assert db_task.status == TaskStatus.FAILED

        # Bounty remains AWARDED per specification
        db_bounty = session.get(Bounty, res.bounty.id)
        assert db_bounty.status == BountyStatus.AWARDED

        # Subsequent execution under same authorization is blocked
        with pytest.raises(DuplicatePaymentError, match="previously reached terminal FAILED state"):
            exec_service.execute_payment(req)

    def test_duplicate_execution_on_interrupted_created_transaction(
        self, session: Session, test_settings: Settings, authorized_workflow
    ) -> None:
        res, auth = authorized_workflow
        exec_service = PaymentExecutionService(session=session, settings=test_settings)
        actor = ActorContext(actor_type="HUMAN", actor_id="operator")
        req = PaymentExecutionRequest(authorization_id=auth.id, actor=actor)

        # Manually create a CREATED transaction to simulate process crash before SUBMITTED
        idemp_key = exec_service.derive_idempotency_key(auth.id, res.task.id)
        from agentbounty.persistence.repositories import PaymentTransactionRepository
        from agentbounty.domain.enums import PaymentExecutionMode
        tx_repo = PaymentTransactionRepository(session)
        created_tx = tx_repo.create(
            task_id=res.task.id,
            bounty_id=res.bounty.id,
            authorization_id=auth.id,
            provider_name="mock",
            execution_mode=PaymentExecutionMode.SIMULATED,
            amount_minor_units=auth.authorized_amount,
            idempotency_key=idemp_key,
        )

        dup_res = exec_service.execute_payment(req)
        assert dup_res.is_duplicate is True
        assert dup_res.transaction.id == created_tx.id
        assert dup_res.status == PaymentStatus.CREATED
