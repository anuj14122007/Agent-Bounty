"""Unit and integration tests for PaymentAuthorizationService."""

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
from agentbounty.domain.money import Money
from agentbounty.exceptions import (
    BountyAmountMismatchError,
    BudgetExceededError,
    CurrencyMismatchError,
    DuplicatePaymentError,
    EntityNotFoundError,
    InvalidAuthorizationError,
    InvalidMoneyError,
    InvalidStateTransitionError,
    UnauthorizedActorError,
    VerificationNotPassedError,
)
from agentbounty.payments.authorization import PaymentAuthorizationService
from agentbounty.payments.schemas import ActorContext, AuthorizationRequest, RevocationRequest
from agentbounty.persistence.models import Bounty, Task
from agentbounty.persistence.repositories import (
    AuditEventRepository,
    PaymentTransactionRepository,
)
from agentbounty.services.task_orchestration import TaskOrchestrationService


@pytest.fixture
def auth_service(session: Session, test_settings: Settings) -> PaymentAuthorizationService:
    return PaymentAuthorizationService(session=session, settings=test_settings)


@pytest.fixture
def prepared_task(session: Session, test_settings: Settings):
    """Run full workflow up to AWAITING_AUTHORIZATION."""
    registry = AgentRegistry()
    registry.sync_with_db(session)
    orchestrator = TaskOrchestrationService(
        session=session,
        registry=registry,
        settings=test_settings,
    )
    res = orchestrator.run_full_workflow(
        title="Sample Product Overview",
        description="Introduction for AgentBounty with professional overview.",
        acceptance_criteria=["contains:AgentBounty", "min_words:10"],
        created_by="alice_founder",
        proposed_bounty=Decimal("3.50"),
    )
    return res


class TestPaymentAuthorizationService:
    """Test suite covering financial authorization governance."""

    def test_valid_human_authorization(
        self, auth_service: PaymentAuthorizationService, prepared_task, session: Session
    ) -> None:
        actor = ActorContext(actor_type="HUMAN", actor_id="alice_founder")
        req = AuthorizationRequest(
            task_id=prepared_task.task.id,
            bounty_id=prepared_task.bounty.id,
            authorized_amount=Decimal("3.50"),
            currency="USD",
            decision=AuthorizationDecision.AUTHORIZED,
            actor=actor,
            reason="Work satisfies all requirements.",
        )

        auth = auth_service.authorize_payment(req)
        assert auth.id is not None
        assert auth.decision == AuthorizationDecision.AUTHORIZED
        assert auth.authorized_amount == 350
        assert auth.currency == "USD"
        assert auth.authorized_by == "alice_founder"

        # Verify audit event
        audit_repo = AuditEventRepository(session)
        events = audit_repo.list_by_entity("payment_authorization", auth.id)
        assert len(events) >= 1
        assert events[0].event_type == "PAYMENT_AUTHORIZED"

    @pytest.mark.parametrize("disallowed_role", ["MANAGER", "WORKER", "SYSTEM"])
    def test_non_human_actors_rejected(
        self, auth_service: PaymentAuthorizationService, prepared_task, disallowed_role: str
    ) -> None:
        actor = ActorContext(actor_type=disallowed_role, actor_id="agent_007")
        req = AuthorizationRequest(
            task_id=prepared_task.task.id,
            bounty_id=prepared_task.bounty.id,
            authorized_amount=Decimal("3.50"),
            currency="USD",
            decision=AuthorizationDecision.AUTHORIZED,
            actor=actor,
        )

        with pytest.raises(UnauthorizedActorError, match="Financial authorization is strictly restricted"):
            auth_service.authorize_payment(req)

    def test_task_must_be_awaiting_authorization(
        self, auth_service: PaymentAuthorizationService, prepared_task, session: Session
    ) -> None:
        # Move task to DRAFT
        task = session.get(Task, prepared_task.task.id)
        task.status = TaskStatus.DRAFT
        session.flush()

        actor = ActorContext(actor_type="HUMAN", actor_id="admin")
        req = AuthorizationRequest(
            task_id=prepared_task.task.id,
            bounty_id=prepared_task.bounty.id,
            authorized_amount=Decimal("3.50"),
            actor=actor,
        )
        with pytest.raises(InvalidStateTransitionError, match="cannot be authorized: status is 'DRAFT'"):
            auth_service.authorize_payment(req)

    def test_bounty_must_be_awarded(
        self, auth_service: PaymentAuthorizationService, prepared_task, session: Session
    ) -> None:
        # Move bounty to RESERVED
        bounty = session.get(Bounty, prepared_task.bounty.id)
        bounty.status = BountyStatus.RESERVED
        session.flush()

        actor = ActorContext(actor_type="HUMAN", actor_id="admin")
        req = AuthorizationRequest(
            task_id=prepared_task.task.id,
            bounty_id=prepared_task.bounty.id,
            authorized_amount=Decimal("3.50"),
            actor=actor,
        )
        with pytest.raises(InvalidStateTransitionError, match="cannot be authorized: status is 'RESERVED'"):
            auth_service.authorize_payment(req)

    def test_verification_must_be_passed(
        self, auth_service: PaymentAuthorizationService, session: Session, test_settings: Settings
    ) -> None:
        registry = AgentRegistry()
        registry.sync_with_db(session)
        orchestrator = TaskOrchestrationService(session=session, registry=registry, settings=test_settings)
        # Create a task that requires human review
        res = orchestrator.run_full_workflow(
            title="Write Creative Brand Manifesto",
            description="Please write an introduction.",
            acceptance_criteria=[
                "contains:Introduction",
                "The piece must sound deeply soulful and avant-garde",
            ],
            created_by="founder",
            proposed_bounty=Decimal("2.00"),
        )

        actor = ActorContext(actor_type="HUMAN", actor_id="admin")
        req = AuthorizationRequest(
            task_id=res.task.id,
            bounty_id=res.bounty.id,
            authorized_amount=Decimal("2.00"),
            actor=actor,
        )
        with pytest.raises(InvalidStateTransitionError):
            auth_service.authorize_payment(req)

    def test_amount_mismatch_rejected(
        self, auth_service: PaymentAuthorizationService, prepared_task
    ) -> None:
        actor = ActorContext(actor_type="HUMAN", actor_id="alice_founder")
        req = AuthorizationRequest(
            task_id=prepared_task.task.id,
            bounty_id=prepared_task.bounty.id,
            authorized_amount=Decimal("2.00"),  # bounty is 3.50
            actor=actor,
        )
        with pytest.raises(BountyAmountMismatchError, match="does not match bounty amount"):
            auth_service.authorize_payment(req)

    def test_currency_mismatch_rejected(
        self, auth_service: PaymentAuthorizationService, prepared_task
    ) -> None:
        actor = ActorContext(actor_type="HUMAN", actor_id="alice_founder")
        req = AuthorizationRequest(
            task_id=prepared_task.task.id,
            bounty_id=prepared_task.bounty.id,
            authorized_amount=Decimal("3.50"),
            currency="EUR",  # bounty is USD
            actor=actor,
        )
        with pytest.raises(CurrencyMismatchError, match="Authorized currency 'EUR' does not match"):
            auth_service.authorize_payment(req)

    def test_exceeding_max_bounty_ceiling_rejected(
        self, auth_service: PaymentAuthorizationService, prepared_task, session: Session
    ) -> None:
        # Artificially set bounty to 150.00
        bounty = session.get(Bounty, prepared_task.bounty.id)
        bounty.amount = 15000
        session.flush()

        actor = ActorContext(actor_type="HUMAN", actor_id="alice_founder")
        req = AuthorizationRequest(
            task_id=prepared_task.task.id,
            bounty_id=prepared_task.bounty.id,
            authorized_amount=Decimal("150.00"),
            actor=actor,
        )
        with pytest.raises(BudgetExceededError, match="exceeds MAX_BOUNTY_USD ceiling"):
            auth_service.authorize_payment(req)

    def test_rejection_updates_task_and_bounty(
        self, auth_service: PaymentAuthorizationService, prepared_task, session: Session
    ) -> None:
        actor = ActorContext(actor_type="HUMAN", actor_id="reviewer_bob")
        req = AuthorizationRequest(
            task_id=prepared_task.task.id,
            bounty_id=prepared_task.bounty.id,
            authorized_amount=Decimal("3.50"),
            decision=AuthorizationDecision.REJECTED,
            actor=actor,
            reason="Deliverable quality does not meet publication standards.",
        )

        auth = auth_service.authorize_payment(req)
        assert auth.decision == AuthorizationDecision.REJECTED

        # Check DB states
        db_task = session.get(Task, prepared_task.task.id)
        db_bounty = session.get(Bounty, prepared_task.bounty.id)
        assert db_task.status == TaskStatus.REJECTED
        assert db_bounty.status == BountyStatus.CANCELLED

        # Check audit trail
        audit_repo = AuditEventRepository(session)
        events = [e.event_type for e in audit_repo.list_by_entity("payment_authorization", auth.id)]
        assert "PAYMENT_REJECTED" in events

    def test_revocation_before_submission(
        self, auth_service: PaymentAuthorizationService, prepared_task, session: Session
    ) -> None:
        actor = ActorContext(actor_type="HUMAN", actor_id="alice_founder")
        req = AuthorizationRequest(
            task_id=prepared_task.task.id,
            bounty_id=prepared_task.bounty.id,
            authorized_amount=Decimal("3.50"),
            actor=actor,
        )
        auth = auth_service.authorize_payment(req)
        assert auth.decision == AuthorizationDecision.AUTHORIZED

        # Revoke authorization
        rev_req = RevocationRequest(
            authorization_id=auth.id,
            actor=actor,
            reason="Found errors in final copy, pausing payout.",
        )
        revoked = auth_service.revoke_authorization(rev_req)
        assert revoked.decision == AuthorizationDecision.REVOKED

        # Task and bounty should remain AWAITING_AUTHORIZATION and AWARDED
        db_task = session.get(Task, prepared_task.task.id)
        db_bounty = session.get(Bounty, prepared_task.bounty.id)
        assert db_task.status == TaskStatus.AWAITING_AUTHORIZATION
        assert db_bounty.status == BountyStatus.AWARDED

    def test_revocation_after_submission_rejected(
        self, auth_service: PaymentAuthorizationService, prepared_task, session: Session
    ) -> None:
        actor = ActorContext(actor_type="HUMAN", actor_id="alice_founder")
        req = AuthorizationRequest(
            task_id=prepared_task.task.id,
            bounty_id=prepared_task.bounty.id,
            authorized_amount=Decimal("3.50"),
            actor=actor,
        )
        auth = auth_service.authorize_payment(req)

        # Create a SUBMITTED transaction
        tx_repo = PaymentTransactionRepository(session)
        tx = tx_repo.create(
            task_id=prepared_task.task.id,
            bounty_id=prepared_task.bounty.id,
            authorization_id=auth.id,
            provider_name="mock",
            execution_mode=PaymentExecutionMode.SIMULATED,
            amount_minor_units=auth.authorized_amount,
            idempotency_key="idemp_test_12345",
        )
        tx_repo.update_status(tx.id, PaymentStatus.SUBMITTED)

        rev_req = RevocationRequest(
            authorization_id=auth.id,
            actor=actor,
            reason="Attempting late revocation.",
        )
        with pytest.raises(InvalidStateTransitionError, match="Payment submission has already commenced"):
            auth_service.revoke_authorization(rev_req)
