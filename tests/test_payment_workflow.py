"""End-to-end integration tests for AgentBounty Payment Workflows."""

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
    VerificationStatus,
)
from agentbounty.exceptions import ProviderTimeoutError
from agentbounty.payments.authorization import PaymentAuthorizationService
from agentbounty.payments.execution import PaymentExecutionService
from agentbounty.payments.ledger import TransactionLedgerService
from agentbounty.payments.providers.mock import MockPaymentProvider
from agentbounty.payments.reconciliation import PaymentReconciliationService
from agentbounty.payments.schemas import (
    ActorContext,
    AuthorizationRequest,
    PaymentExecutionRequest,
    RevocationRequest,
)
from agentbounty.persistence.repositories import (
    AuditEventRepository,
    BountyRepository,
    PaymentAuthorizationRepository,
    PaymentTransactionRepository,
    TaskRepository,
)
from agentbounty.services.task_orchestration import TaskOrchestrationService


class TestPaymentWorkflowEndToEnd:
    """Complete multi-phase integration tests from task creation through ledger verification."""

    def test_full_demo_workflow_end_to_end(
        self, session: Session, test_settings: Settings
    ) -> None:
        """Complete happy path: submission -> delegation -> execution -> verification -> authorization -> payment -> completion."""
        registry = AgentRegistry()
        registry.sync_with_db(session)
        orchestrator = TaskOrchestrationService(session=session, registry=registry, settings=test_settings)

        # 1. Human submits task and orchestrator runs worker + verification
        workflow_res = orchestrator.run_full_workflow(
            title="Compose Product Announcement",
            description="Write an introduction announcement for our new AI safety toolkit.",
            acceptance_criteria=["contains:toolkit", "min_words:5"],
            created_by="founder_carol",
            proposed_bounty=Decimal("4.50"),
        )

        assert workflow_res.task.status == TaskStatus.AWAITING_AUTHORIZATION
        assert workflow_res.bounty.status == BountyStatus.AWARDED
        assert workflow_res.verification.status == VerificationStatus.PASSED

        # 2. Human reviews deliverable and authorizes payment
        human_actor = ActorContext(actor_type="HUMAN", actor_id="founder_carol")
        auth_service = PaymentAuthorizationService(session=session, settings=test_settings)
        auth = auth_service.authorize_payment(
            AuthorizationRequest(
                task_id=workflow_res.task.id,
                bounty_id=workflow_res.bounty.id,
                authorized_amount=Decimal("4.50"),
                currency="USD",
                actor=human_actor,
                reason="Quality verified and accepted.",
            )
        )

        assert auth.decision == AuthorizationDecision.AUTHORIZED
        assert auth.authorized_amount == 450

        # 3. Human triggers payment execution via offline Mock provider
        mock_provider = MockPaymentProvider()
        exec_service = PaymentExecutionService(
            session=session,
            settings=test_settings,
            provider=mock_provider,
        )
        exec_res = exec_service.execute_payment(
            PaymentExecutionRequest(
                authorization_id=auth.id,
                actor=human_actor,
            )
        )

        # 4. Verify transaction execution result
        assert exec_res.status == PaymentStatus.SUCCEEDED
        assert exec_res.is_duplicate is False
        assert exec_res.transaction.status == PaymentStatus.SUCCEEDED
        assert exec_res.transaction.execution_mode == PaymentExecutionMode.SIMULATED
        assert exec_res.transaction.external_reference is None
        assert exec_res.task.status == TaskStatus.COMPLETED
        assert exec_res.bounty.status == BountyStatus.PAID

        # 5. Verify database state
        task_repo = TaskRepository(session)
        bounty_repo = BountyRepository(session)
        db_task = task_repo.get_by_id(workflow_res.task.id)
        db_bounty = bounty_repo.get_by_id(workflow_res.bounty.id)
        assert db_task.status == TaskStatus.COMPLETED
        assert db_bounty.status == BountyStatus.PAID

        # 6. Verify persistent ledger and audit trail
        ledger = TransactionLedgerService(session=session)
        history = ledger.get_task_payment_history(workflow_res.task.id)
        assert len(history.authorizations) == 1
        assert len(history.transactions) == 1

        event_types = [e.event_type for e in history.audit_events]
        assert "PAYMENT_AUTHORIZED" in event_types
        assert "PAYMENT_SUBMITTED" in event_types
        assert "PAYMENT_SUCCEEDED" in event_types

        # Verify idempotency: duplicate execution returns existing transaction without re-execution
        dup_res = exec_service.execute_payment(
            PaymentExecutionRequest(
                authorization_id=auth.id,
                actor=human_actor,
            )
        )
        assert dup_res.is_duplicate is True
        assert dup_res.transaction.id == exec_res.transaction.id
        assert mock_provider.submission_count == 1  # Only one provider payout call!

    def test_full_workflow_human_rejection(
        self, session: Session, test_settings: Settings
    ) -> None:
        """Human rejects authorization: task REJECTED, bounty CANCELLED, no payment transaction."""
        registry = AgentRegistry()
        registry.sync_with_db(session)
        orchestrator = TaskOrchestrationService(session=session, registry=registry, settings=test_settings)

        workflow_res = orchestrator.run_full_workflow(
            title="Compose Product Announcement",
            description="Write an introduction announcement for our new AI safety toolkit.",
            acceptance_criteria=["contains:toolkit"],
            created_by="founder_dave",
            proposed_bounty=Decimal("2.50"),
        )
        assert workflow_res.task.status == TaskStatus.AWAITING_AUTHORIZATION
        assert workflow_res.bounty.status == BountyStatus.AWARDED

        # Human rejects
        human_actor = ActorContext(actor_type="HUMAN", actor_id="founder_dave")
        auth_service = PaymentAuthorizationService(session=session, settings=test_settings)
        auth = auth_service.authorize_payment(
            AuthorizationRequest(
                task_id=workflow_res.task.id,
                bounty_id=workflow_res.bounty.id,
                authorized_amount=Decimal("2.50"),
                currency="USD",
                decision=AuthorizationDecision.REJECTED,
                actor=human_actor,
                reason="Work does not meet brand voice guidelines.",
            )
        )

        assert auth.decision == AuthorizationDecision.REJECTED

        # Database state: task is REJECTED, bounty is CANCELLED
        task_repo = TaskRepository(session)
        bounty_repo = BountyRepository(session)
        db_task = task_repo.get_by_id(workflow_res.task.id)
        db_bounty = bounty_repo.get_by_id(workflow_res.bounty.id)
        assert db_task.status == TaskStatus.REJECTED
        assert db_bounty.status == BountyStatus.CANCELLED

        # Ledger: no transactions created
        ledger = TransactionLedgerService(session=session)
        txs = ledger.list_transactions(task_id=workflow_res.task.id)
        assert len(txs) == 0

        # Audit events contain rejection
        audit_repo = AuditEventRepository(session)
        auth_events = [e.event_type for e in audit_repo.list_by_entity("payment_authorization", auth.id)]
        bounty_events = [e.event_type for e in audit_repo.list_by_entity("bounty", workflow_res.bounty.id)]
        assert "PAYMENT_REJECTED" in auth_events
        assert "BOUNTY_CANCELLED" in bounty_events

    def test_full_workflow_timeout_and_reconciliation(
        self, session: Session, test_settings: Settings
    ) -> None:
        """Simulate provider timeout (UNKNOWN) followed by reconciliation recovering SUCCEEDED state."""
        registry = AgentRegistry()
        registry.sync_with_db(session)
        orchestrator = TaskOrchestrationService(session=session, registry=registry, settings=test_settings)

        workflow_res = orchestrator.run_full_workflow(
            title="Compose Product Announcement",
            description="Write an introduction announcement for our new AI safety toolkit.",
            acceptance_criteria=["contains:toolkit"],
            created_by="founder_eve",
            proposed_bounty=Decimal("3.00"),
        )

        human_actor = ActorContext(actor_type="HUMAN", actor_id="founder_eve")
        auth_service = PaymentAuthorizationService(session=session, settings=test_settings)
        auth = auth_service.authorize_payment(
            AuthorizationRequest(
                task_id=workflow_res.task.id,
                bounty_id=workflow_res.bounty.id,
                authorized_amount=Decimal("3.00"),
                currency="USD",
                actor=human_actor,
            )
        )

        # Provider initially simulates timeout
        mock_provider = MockPaymentProvider(simulate_timeout=True)
        exec_service = PaymentExecutionService(
            session=session,
            settings=test_settings,
            provider=mock_provider,
        )

        exec_res = exec_service.execute_payment(
            PaymentExecutionRequest(
                authorization_id=auth.id,
                actor=human_actor,
            )
        )

        # Execution result: UNKNOWN, task & bounty in PAYMENT_PENDING
        assert exec_res.status == PaymentStatus.UNKNOWN
        assert exec_res.transaction.status == PaymentStatus.UNKNOWN
        assert exec_res.task.status == TaskStatus.PAYMENT_PENDING
        assert exec_res.bounty.status == BountyStatus.PAYMENT_PENDING

        task_repo = TaskRepository(session)
        bounty_repo = BountyRepository(session)
        assert task_repo.get_by_id(workflow_res.task.id).status == TaskStatus.PAYMENT_PENDING
        assert bounty_repo.get_by_id(workflow_res.bounty.id).status == BountyStatus.PAYMENT_PENDING

        # Now provider is available and status check reports SUCCEEDED
        mock_provider.simulate_timeout = False
        reconciliation_service = PaymentReconciliationService(
            session=session,
            provider=mock_provider,
        )

        recon_res = reconciliation_service.reconcile_transaction(
            transaction_id=exec_res.transaction.id,
        )

        assert recon_res.status == PaymentStatus.SUCCEEDED
        assert task_repo.get_by_id(workflow_res.task.id).status == TaskStatus.COMPLETED
        assert bounty_repo.get_by_id(workflow_res.bounty.id).status == BountyStatus.PAID
