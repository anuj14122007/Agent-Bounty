"""Unit tests for TransactionLedgerService."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from agentbounty.agents.registry import AgentRegistry
from agentbounty.config.settings import Settings
from agentbounty.domain.enums import (
    AuthorizationDecision,
    PaymentExecutionMode,
    PaymentStatus,
)
from agentbounty.exceptions import EntityNotFoundError
from agentbounty.payments.authorization import PaymentAuthorizationService
from agentbounty.payments.execution import PaymentExecutionService
from agentbounty.payments.ledger import TransactionLedgerService
from agentbounty.payments.providers.mock import MockPaymentProvider
from agentbounty.payments.schemas import ActorContext, AuthorizationRequest, PaymentExecutionRequest
from agentbounty.persistence.repositories import (
    AuditEventRepository,
    BountyRepository,
    PaymentAuthorizationRepository,
    PaymentTransactionRepository,
    TaskRepository,
)
from agentbounty.services.task_orchestration import TaskOrchestrationService


@pytest.fixture
def ledger_service(session: Session) -> TransactionLedgerService:
    return TransactionLedgerService(session=session)


@pytest.fixture
def prepared_task(session: Session, test_settings: Settings):
    """Create a task that has passed verification and is awaiting payment authorization."""
    registry = AgentRegistry()
    registry.sync_with_db(session)
    orchestrator = TaskOrchestrationService(session=session, registry=registry, settings=test_settings)
    return orchestrator.run_full_workflow(
        title="Sample Product Overview",
        description="Introduction for AgentBounty with professional overview.",
        acceptance_criteria=["contains:AgentBounty", "min_words:10"],
        created_by="founder_alice",
        proposed_bounty=Decimal("3.00"),
    )


class TestTransactionLedgerService:
    def test_get_transaction_and_get_or_raise(
        self,
        ledger_service: TransactionLedgerService,
        prepared_task,
        session: Session,
        test_settings: Settings,
    ) -> None:
        auth_service = PaymentAuthorizationService(session, test_settings)
        auth = auth_service.authorize_payment(
            AuthorizationRequest(
                task_id=prepared_task.task.id,
                bounty_id=prepared_task.bounty.id,
                authorized_amount=Decimal("3.00"),
                actor=ActorContext(actor_type="HUMAN", actor_id="alice"),
            )
        )

        mock_provider = MockPaymentProvider()
        exec_service = PaymentExecutionService(
            session=session,
            settings=test_settings,
            provider=mock_provider,
        )
        res = exec_service.execute_payment(
            PaymentExecutionRequest(
                authorization_id=auth.id,
                actor=ActorContext(actor_type="HUMAN", actor_id="alice"),
            )
        )

        # 1. get_transaction
        found = ledger_service.get_transaction(res.transaction.id)
        assert found is not None
        assert found.id == res.transaction.id
        assert found.amount == 300
        assert found.status == PaymentStatus.SUCCEEDED
        assert found.execution_mode == PaymentExecutionMode.SIMULATED

        missing = ledger_service.get_transaction("nonexistent_id")
        assert missing is None

        # 2. get_transaction_or_raise
        found_raise = ledger_service.get_transaction_or_raise(res.transaction.id)
        assert found_raise.id == res.transaction.id

        with pytest.raises(EntityNotFoundError, match="not found in ledger"):
            ledger_service.get_transaction_or_raise("nonexistent_id")

    def test_list_transactions_filters(
        self,
        ledger_service: TransactionLedgerService,
        prepared_task,
        session: Session,
        test_settings: Settings,
    ) -> None:
        tx_repo = PaymentTransactionRepository(session)
        now = datetime.now(timezone.utc)

        # Create second task & bounty for distinct task_id testing
        task_repo = TaskRepository(session)
        bounty_repo = BountyRepository(session)
        other_task = task_repo.create(
            title="Second task",
            description="Other description",
            acceptance_criteria=["rule"],
            created_by="founder",
        )
        other_bounty = bounty_repo.create(
            task_id=other_task.id,
            amount_minor_units=500,
            currency="USD",
        )

        # Create diverse transactions
        t1 = tx_repo.create(
            task_id=prepared_task.task.id,
            bounty_id=prepared_task.bounty.id,
            provider_name="mock",
            execution_mode=PaymentExecutionMode.SIMULATED,
            amount_minor_units=100,
            idempotency_key="idemp_1",
        )
        tx_repo.update_status(t1.id, PaymentStatus.SUCCEEDED)

        t2 = tx_repo.create(
            task_id=prepared_task.task.id,
            bounty_id=prepared_task.bounty.id,
            provider_name="mock",
            execution_mode=PaymentExecutionMode.SIMULATED,
            amount_minor_units=200,
            idempotency_key="idemp_2",
        )
        tx_repo.update_status(t2.id, PaymentStatus.FAILED)

        t3 = tx_repo.create(
            task_id=other_task.id,
            bounty_id=other_bounty.id,
            provider_name="paypal_sandbox",
            execution_mode=PaymentExecutionMode.SANDBOX,
            amount_minor_units=500,
            idempotency_key="idemp_3",
        )
        tx_repo.update_status(t3.id, PaymentStatus.PENDING)

        # Filter by status
        succeeded = ledger_service.list_transactions(status=PaymentStatus.SUCCEEDED)
        assert any(t.id == t1.id for t in succeeded)
        assert all(t.status == PaymentStatus.SUCCEEDED for t in succeeded)

        failed = ledger_service.list_transactions(status=PaymentStatus.FAILED)
        assert any(t.id == t2.id for t in failed)

        # Filter by provider
        paypal = ledger_service.list_transactions(provider_name="paypal_sandbox")
        assert len(paypal) == 1
        assert paypal[0].id == t3.id

        # Filter by execution mode
        sandbox = ledger_service.list_transactions(execution_mode=PaymentExecutionMode.SANDBOX)
        assert len(sandbox) == 1
        assert sandbox[0].id == t3.id

        simulated = ledger_service.list_transactions(execution_mode=PaymentExecutionMode.SIMULATED)
        assert len(simulated) >= 2

        # Filter by task_id
        task_txs = ledger_service.list_transactions(task_id=prepared_task.task.id)
        assert len(task_txs) == 2
        assert {t.id for t in task_txs} == {t1.id, t2.id}

        # Filter by date range
        future_txs = ledger_service.list_transactions(start_time=now + timedelta(days=1))
        assert len(future_txs) == 0

        past_txs = ledger_service.list_transactions(end_time=now + timedelta(minutes=5))
        assert len(past_txs) >= 3

        # Pagination limit and offset
        page1 = ledger_service.list_transactions(limit=1, offset=0)
        assert len(page1) == 1
        page2 = ledger_service.list_transactions(limit=1, offset=1)
        assert len(page2) == 1
        assert page1[0].id != page2[0].id

    def test_get_task_payment_history(
        self,
        ledger_service: TransactionLedgerService,
        prepared_task,
        session: Session,
        test_settings: Settings,
    ) -> None:
        auth_service = PaymentAuthorizationService(session, test_settings)
        auth = auth_service.authorize_payment(
            AuthorizationRequest(
                task_id=prepared_task.task.id,
                bounty_id=prepared_task.bounty.id,
                authorized_amount=Decimal("3.00"),
                actor=ActorContext(actor_type="HUMAN", actor_id="alice"),
            )
        )

        mock_provider = MockPaymentProvider()
        exec_service = PaymentExecutionService(
            session=session,
            settings=test_settings,
            provider=mock_provider,
        )
        res = exec_service.execute_payment(
            PaymentExecutionRequest(
                authorization_id=auth.id,
                actor=ActorContext(actor_type="HUMAN", actor_id="alice"),
            )
        )

        history = ledger_service.get_task_payment_history(prepared_task.task.id)
        assert history.task_id == prepared_task.task.id
        assert len(history.authorizations) == 1
        assert history.authorizations[0].id == auth.id
        assert history.authorizations[0].decision == AuthorizationDecision.AUTHORIZED

        assert len(history.transactions) == 1
        assert history.transactions[0].id == res.transaction.id
        assert history.transactions[0].status == PaymentStatus.SUCCEEDED

        # Audit events must include authorization and execution events
        event_types = [e.event_type for e in history.audit_events]
        assert "PAYMENT_AUTHORIZED" in event_types
        assert "PAYMENT_SUBMITTED" in event_types
        assert "PAYMENT_SUCCEEDED" in event_types
