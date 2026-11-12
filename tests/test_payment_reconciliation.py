"""Unit and integration tests for PaymentReconciliationService."""

from __future__ import annotations

from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from agentbounty.agents.registry import AgentRegistry
from agentbounty.config.settings import Settings
from agentbounty.domain.enums import (
    AuthorizationDecision,
    BountyStatus,
    PaymentStatus,
    TaskStatus,
)
from agentbounty.exceptions import EntityNotFoundError
from agentbounty.payments.authorization import PaymentAuthorizationService
from agentbounty.payments.execution import PaymentExecutionService
from agentbounty.payments.providers.mock import MockPaymentProvider
from agentbounty.payments.reconciliation import PaymentReconciliationService
from agentbounty.payments.schemas import ActorContext, AuthorizationRequest, PaymentExecutionRequest
from agentbounty.persistence.models import Bounty, PaymentTransaction, Task
from agentbounty.persistence.repositories import AuditEventRepository
from agentbounty.services.task_orchestration import TaskOrchestrationService


@pytest.fixture
def pending_or_unknown_payment(session: Session, test_settings: Settings):
    """Set up a workflow that stops in UNKNOWN state due to simulated timeout."""
    registry = AgentRegistry()
    registry.sync_with_db(session)
    orchestrator = TaskOrchestrationService(session=session, registry=registry, settings=test_settings)
    res = orchestrator.run_full_workflow(
        title="Reconciliation Test Task",
        description="Introduction for AgentBounty.",
        acceptance_criteria=["contains:AgentBounty", "min_words:5"],
        created_by="founder",
        proposed_bounty=Decimal("2.50"),
    )

    auth_service = PaymentAuthorizationService(session=session, settings=test_settings)
    auth = auth_service.authorize_payment(
        AuthorizationRequest(
            task_id=res.task.id,
            bounty_id=res.bounty.id,
            authorized_amount=Decimal("2.50"),
            currency="USD",
            decision=AuthorizationDecision.AUTHORIZED,
            actor=ActorContext(actor_type="HUMAN", actor_id="founder"),
        )
    )

    # Execute with timeout to produce UNKNOWN status
    timeout_provider = MockPaymentProvider(simulate_timeout=True)
    exec_service = PaymentExecutionService(session=session, provider=timeout_provider, settings=test_settings)
    exec_res = exec_service.execute_payment(
        PaymentExecutionRequest(authorization_id=auth.id, actor=ActorContext(actor_type="HUMAN", actor_id="operator"))
    )
    assert exec_res.status == PaymentStatus.UNKNOWN

    return res, auth, exec_res.transaction


class TestPaymentReconciliationService:
    """Test suite covering payment reconciliation."""

    def test_reconcile_unknown_to_succeeded(
        self, session: Session, pending_or_unknown_payment
    ) -> None:
        res, auth, tx_read = pending_or_unknown_payment
        # Provider now returns SUCCEEDED on status check
        provider = MockPaymentProvider(default_status=PaymentStatus.SUCCEEDED)
        recon_service = PaymentReconciliationService(session=session, provider=provider)

        reconciled = recon_service.reconcile_transaction(tx_read.id)
        assert reconciled.status == PaymentStatus.SUCCEEDED

        # Database models must be updated
        db_tx = session.get(PaymentTransaction, tx_read.id)
        assert db_tx.status == PaymentStatus.SUCCEEDED

        db_task = session.get(Task, res.task.id)
        assert db_task.status == TaskStatus.COMPLETED

        db_bounty = session.get(Bounty, res.bounty.id)
        assert db_bounty.status == BountyStatus.PAID

        # Audit events
        audit_repo = AuditEventRepository(session)
        events = [e.event_type for e in audit_repo.list_by_entity("payment_transaction", tx_read.id)]
        assert "PAYMENT_RECONCILED" in events
        assert "PAYMENT_SUCCEEDED" in events

    def test_reconcile_unknown_to_failed(
        self, session: Session, pending_or_unknown_payment
    ) -> None:
        res, auth, tx_read = pending_or_unknown_payment
        provider = MockPaymentProvider(simulate_failure=True)
        recon_service = PaymentReconciliationService(session=session, provider=provider)

        reconciled = recon_service.reconcile_transaction(tx_read.id)
        assert reconciled.status == PaymentStatus.FAILED

        db_tx = session.get(PaymentTransaction, tx_read.id)
        assert db_tx.status == PaymentStatus.FAILED

        db_task = session.get(Task, res.task.id)
        assert db_task.status == TaskStatus.FAILED

        db_bounty = session.get(Bounty, res.bounty.id)
        assert db_bounty.status == BountyStatus.AWARDED

    def test_reconcile_unknown_stays_unknown_on_provider_timeout(
        self, session: Session, pending_or_unknown_payment
    ) -> None:
        res, auth, tx_read = pending_or_unknown_payment
        # Provider still times out
        provider = MockPaymentProvider(simulate_timeout=True)
        recon_service = PaymentReconciliationService(session=session, provider=provider)

        reconciled = recon_service.reconcile_transaction(tx_read.id)
        assert reconciled.status == PaymentStatus.UNKNOWN

        # Never falsely infer success
        db_task = session.get(Task, res.task.id)
        assert db_task.status == TaskStatus.PAYMENT_PENDING

    def test_reconcile_already_succeeded_is_idempotent(
        self, session: Session, pending_or_unknown_payment
    ) -> None:
        res, auth, tx_read = pending_or_unknown_payment
        provider = MockPaymentProvider(default_status=PaymentStatus.SUCCEEDED)
        recon_service = PaymentReconciliationService(session=session, provider=provider)

        first = recon_service.reconcile_transaction(tx_read.id)
        assert first.status == PaymentStatus.SUCCEEDED

        # Second call is idempotent
        second = recon_service.reconcile_transaction(tx_read.id)
        assert second.status == PaymentStatus.SUCCEEDED
        assert second.id == first.id

    def test_reconcile_non_existent_transaction_raises(
        self, session: Session
    ) -> None:
        recon_service = PaymentReconciliationService(session=session)
        with pytest.raises(EntityNotFoundError, match="PaymentTransaction with ID '.*' not found"):
            recon_service.reconcile_transaction("missing-tx-id")
