"""Tests for UI services, application bootstrap, dashboard metrics, and financial safeguards."""

from __future__ import annotations

from decimal import Decimal
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentbounty.agents.profiles import (
    CODE_ASSISTANT_ID,
    CREATIVE_WRITER_ID,
    DATA_ANALYST_ID,
    MANAGER_AGENT_ID,
    RESEARCHER_ID,
)
from agentbounty.config.settings import Settings
from agentbounty.domain.enums import (
    AgentRole,
    AuthorizationDecision,
    BountyStatus,
    PaymentExecutionMode,
    PaymentStatus,
    TaskStatus,
    VerificationStatus,
)
from agentbounty.domain.money import from_minor_units
from agentbounty.exceptions import (
    BountyAmountMismatchError,
    BudgetExceededError,
    InvalidStateTransitionError,
    UnauthorizedActorError,
    VerificationNotPassedError,
)
from agentbounty.payments.authorization import PaymentAuthorizationService
from agentbounty.payments.execution import PaymentExecutionService
from agentbounty.payments.ledger import TransactionLedgerService
from agentbounty.payments.providers.mock import MockPaymentProvider
from agentbounty.payments.reconciliation import PaymentReconciliationService
from agentbounty.payments.schemas import (
    ActorContext,
    AuthorizationRequest,
    PaymentExecutionRequest,
)
from agentbounty.persistence.models import (
    Agent,
    AuditEvent,
    Bounty,
    PaymentAuthorization,
    PaymentTransaction,
    Task,
)
from agentbounty.persistence.repositories import (
    AgentRepository,
    BountyRepository,
    PaymentAuthorizationRepository,
    PaymentTransactionRepository,
    TaskRepository,
)
from ui.bootstrap import (
    AppServices,
    get_app_services,
    get_payment_provider,
    sync_registry_agents,
)
from ui.pages.dashboard import get_dashboard_metrics, get_task_lifecycle_counts


class TestUIBootstrap:
    """Tests for safe application bootstrapping and agent registration."""

    def test_sync_registry_registers_all_five_agents(self, session: Session) -> None:
        """Bootstrap must synchronize Manager and 4 specialist workers with deterministic identities."""
        registry = sync_registry_agents(session)
        agent_repo = AgentRepository(session)
        db_agents = agent_repo.list_all()

        assert len(db_agents) == 5
        agent_ids = {a.id for a in db_agents}
        expected_ids = {
            MANAGER_AGENT_ID,
            CREATIVE_WRITER_ID,
            RESEARCHER_ID,
            DATA_ANALYST_ID,
            CODE_ASSISTANT_ID,
        }
        assert agent_ids == expected_ids

    def test_agent_sync_idempotent_no_duplicates(self, session: Session) -> None:
        """Calling sync_registry_agents repeatedly must never create duplicate records."""
        sync_registry_agents(session)
        sync_registry_agents(session)
        sync_registry_agents(session)

        count = session.scalar(select(func.count(Agent.id)))
        assert count == 5

    def test_payment_provider_defaults_to_mock_in_demo(self, test_settings: Settings) -> None:
        """In DEMO mode, payment provider must strictly instantiate MockPaymentProvider."""
        provider = get_payment_provider(test_settings)
        assert isinstance(provider, MockPaymentProvider)
        assert provider.provider_name == "mock"


class TestDashboardMetrics:
    """Tests for dashboard metrics queried directly from database."""

    def test_dashboard_metrics_empty_database(self, session: Session) -> None:
        """Empty database must yield 0 for all metrics without crashing."""
        sync_registry_agents(session)
        metrics = get_dashboard_metrics(session)

        assert metrics["total_tasks"] == 0
        assert metrics["active_tasks"] == 0
        assert metrics["completed_tasks"] == 0
        assert metrics["total_bounty_usd"] == Decimal("0.00")
        assert metrics["pending_authorizations"] == 0
        assert metrics["successful_payments"] == 0

    def test_dashboard_metrics_populated_database(
        self, session: Session, test_settings: Settings
    ) -> None:
        """Metrics must update accurately as tasks progress through the workflow."""
        sync_registry_agents(session)
        services = get_app_services(session)

        # 1. Run workflow -> Task in AWAITING_AUTHORIZATION
        wf_res = services.orchestrator.run_full_workflow(
            title="Dashboard Metric Test Task",
            description="Testing dashboard metric queries with creative writer.",
            acceptance_criteria=["contains:Dashboard", "min_words:5"],
            created_by="founder_bob",
            proposed_bounty=Decimal("4.00"),
        )
        session.commit()

        metrics1 = get_dashboard_metrics(session)
        assert metrics1["total_tasks"] == 1
        assert metrics1["active_tasks"] == 1
        assert metrics1["completed_tasks"] == 0
        assert metrics1["total_bounty_usd"] == Decimal("4.00")
        assert metrics1["pending_authorizations"] == 1
        assert metrics1["successful_payments"] == 0

        # 2. Authorize and execute simulated payment
        actor = ActorContext(actor_type="HUMAN", actor_id="founder_bob")
        auth = services.auth_service.authorize_payment(
            AuthorizationRequest(
                task_id=wf_res.task.id,
                bounty_id=wf_res.bounty.id,
                authorized_amount=Decimal("4.00"),
                currency="USD",
                actor=actor,
                decision=AuthorizationDecision.AUTHORIZED,
            )
        )
        services.exec_service.execute_payment(
            PaymentExecutionRequest(authorization_id=auth.id, actor=actor)
        )
        session.commit()

        metrics2 = get_dashboard_metrics(session)
        assert metrics2["total_tasks"] == 1
        assert metrics2["active_tasks"] == 0
        assert metrics2["completed_tasks"] == 1
        assert metrics2["total_bounty_usd"] == Decimal("4.00")
        assert metrics2["pending_authorizations"] == 0
        assert metrics2["successful_payments"] == 1

    def test_task_lifecycle_counts_distribution(
        self, session: Session, test_settings: Settings
    ) -> None:
        """Lifecycle state distribution must categorize tasks correctly."""
        sync_registry_agents(session)
        counts = get_task_lifecycle_counts(session)
        assert isinstance(counts, dict)
        assert counts["OPEN"] == 0
        assert counts["COMPLETED"] == 0


class TestHumanGovernanceSafeguards:
    """Tests enforcing human financial authority and verification prerequisites."""

    def test_manager_agent_cannot_authorize_payment(
        self, session: Session, test_settings: Settings
    ) -> None:
        """Autonomous Manager Agent cannot authorize financial payouts."""
        sync_registry_agents(session)
        services = get_app_services(session)

        wf_res = services.orchestrator.run_full_workflow(
            title="Write Governance Safeguard Article",
            description="Write an introduction article testing agent rejection from financial authorization.",
            acceptance_criteria=["contains:Governance", "min_words:5"],
            created_by="founder_alice",
            proposed_bounty=Decimal("3.00"),
        )
        session.commit()

        manager_actor = ActorContext(actor_type="MANAGER", actor_id="marketplace_manager")
        with pytest.raises(UnauthorizedActorError):
            services.auth_service.authorize_payment(
                AuthorizationRequest(
                    task_id=wf_res.task.id,
                    bounty_id=wf_res.bounty.id,
                    authorized_amount=Decimal("3.00"),
                    currency="USD",
                    actor=manager_actor,
                )
            )

    def test_worker_agent_cannot_authorize_payment(
        self, session: Session, test_settings: Settings
    ) -> None:
        """Specialist Worker Agent cannot authorize payouts."""
        sync_registry_agents(session)
        services = get_app_services(session)

        wf_res = services.orchestrator.run_full_workflow(
            title="Write Worker Safeguard Article",
            description="Write an introduction copy testing worker agent rejection from financial authorization.",
            acceptance_criteria=["contains:Worker", "min_words:5"],
            created_by="founder_alice",
            proposed_bounty=Decimal("2.50"),
        )
        session.commit()

        worker_actor = ActorContext(actor_type="WORKER", actor_id=CREATIVE_WRITER_ID)
        with pytest.raises(UnauthorizedActorError):
            services.auth_service.authorize_payment(
                AuthorizationRequest(
                    task_id=wf_res.task.id,
                    bounty_id=wf_res.bounty.id,
                    authorized_amount=Decimal("2.50"),
                    currency="USD",
                    actor=worker_actor,
                )
            )

    def test_authorization_requires_passed_verification(
        self, session: Session, test_settings: Settings
    ) -> None:
        """Payment cannot be authorized for a task that did not pass verification."""
        sync_registry_agents(session)
        services = get_app_services(session)

        # Submit task with an impossible criterion -> Fails verification -> REJECTED
        wf_res = services.orchestrator.run_full_workflow(
            title="Write Failing Criteria Article",
            description="Write an article that intentionally fails verification.",
            acceptance_criteria=["contains:ImpossibleStringXYZ999"],
            created_by="founder_carol",
            proposed_bounty=Decimal("1.50"),
        )
        session.commit()

        assert wf_res.task.status == TaskStatus.REJECTED
        assert wf_res.verification.status == VerificationStatus.FAILED

        human_actor = ActorContext(actor_type="HUMAN", actor_id="founder_carol")
        with pytest.raises((VerificationNotPassedError, InvalidStateTransitionError)):
            services.auth_service.authorize_payment(
                AuthorizationRequest(
                    task_id=wf_res.task.id,
                    bounty_id=wf_res.bounty.id,
                    authorized_amount=Decimal("1.50"),
                    currency="USD",
                    actor=human_actor,
                )
            )

    def test_human_rejection_marks_task_rejected_and_bounty_cancelled(
        self, session: Session, test_settings: Settings
    ) -> None:
        """Explicit human rejection transitions Task to REJECTED and Bounty to CANCELLED."""
        sync_registry_agents(session)
        services = get_app_services(session)

        wf_res = services.orchestrator.run_full_workflow(
            title="Write Task for Human Rejection",
            description="Write an article testing explicit human rejection path.",
            acceptance_criteria=["contains:Rejection", "min_words:5"],
            created_by="operator_dave",
            proposed_bounty=Decimal("3.00"),
        )
        session.commit()

        human_actor = ActorContext(actor_type="HUMAN", actor_id="operator_dave")
        auth_read = services.auth_service.authorize_payment(
            AuthorizationRequest(
                task_id=wf_res.task.id,
                bounty_id=wf_res.bounty.id,
                authorized_amount=Decimal("3.00"),
                currency="USD",
                actor=human_actor,
                decision=AuthorizationDecision.REJECTED,
                reason="Editorial tone did not match guidelines.",
            )
        )
        session.commit()

        assert auth_read.decision == AuthorizationDecision.REJECTED

        # Verify DB records
        task_repo = TaskRepository(session)
        bounty_repo = BountyRepository(session)
        db_task = task_repo.get_by_id(wf_res.task.id)
        db_bounty = bounty_repo.get_by_id(wf_res.bounty.id)

        assert db_task.status == TaskStatus.REJECTED
        assert db_bounty.status == BountyStatus.CANCELLED


class TestPaymentExecutionAndLedger:
    """Tests for simulated payment execution, idempotency, and ledger queries."""

    def test_zero_automatic_payment_execution(
        self, session: Session, test_settings: Settings
    ) -> None:
        """Work completion and verification MUST NOT automatically trigger payment execution."""
        sync_registry_agents(session)
        services = get_app_services(session)

        services.orchestrator.run_full_workflow(
            title="Write Auto Pay Prevention Article",
            description="Write an article verifying that zero transactions are created automatically.",
            acceptance_criteria=["contains:Auto", "min_words:5"],
            created_by="tester",
            proposed_bounty=Decimal("2.00"),
        )
        session.commit()

        tx_count = session.scalar(select(func.count(PaymentTransaction.id)))
        assert tx_count == 0

    def test_payment_execution_simulated_invariants(
        self, session: Session, test_settings: Settings
    ) -> None:
        """Simulated payment execution must produce SIMULATED mode and null external reference."""
        sync_registry_agents(session)
        services = get_app_services(session)

        wf_res = services.orchestrator.run_full_workflow(
            title="Write Simulated Payment Invariants Article",
            description="Write an article verifying simulated provider invariants.",
            acceptance_criteria=["contains:Simulated", "min_words:5"],
            created_by="tester",
            proposed_bounty=Decimal("3.50"),
        )
        session.commit()

        actor = ActorContext(actor_type="HUMAN", actor_id="tester")
        auth = services.auth_service.authorize_payment(
            AuthorizationRequest(
                task_id=wf_res.task.id,
                bounty_id=wf_res.bounty.id,
                authorized_amount=Decimal("3.50"),
                currency="USD",
                actor=actor,
            )
        )
        exec_res = services.exec_service.execute_payment(
            PaymentExecutionRequest(authorization_id=auth.id, actor=actor)
        )
        session.commit()

        assert exec_res.status == PaymentStatus.SUCCEEDED
        assert exec_res.transaction.execution_mode == PaymentExecutionMode.SIMULATED
        assert exec_res.transaction.external_reference is None  # Strict invariant: zero fabricated IDs

    def test_ledger_filtering_by_status_and_mode(
        self, session: Session, test_settings: Settings
    ) -> None:
        """Ledger list_transactions must filter accurately by status and mode."""
        sync_registry_agents(session)
        services = get_app_services(session)

        wf_res = services.orchestrator.run_full_workflow(
            title="Write Ledger Filter Test Article",
            description="Write an article verifying ledger filtered queries.",
            acceptance_criteria=["contains:Ledger", "min_words:5"],
            created_by="tester",
            proposed_bounty=Decimal("2.50"),
        )
        session.commit()

        actor = ActorContext(actor_type="HUMAN", actor_id="tester")
        auth = services.auth_service.authorize_payment(
            AuthorizationRequest(
                task_id=wf_res.task.id,
                bounty_id=wf_res.bounty.id,
                authorized_amount=Decimal("2.50"),
                currency="USD",
                actor=actor,
            )
        )
        services.exec_service.execute_payment(
            PaymentExecutionRequest(authorization_id=auth.id, actor=actor)
        )
        session.commit()

        # Query SUCCEEDED transactions
        succeeded_txs = services.ledger_service.list_transactions(
            status=PaymentStatus.SUCCEEDED,
            execution_mode=PaymentExecutionMode.SIMULATED,
        )
        assert len(succeeded_txs) == 1
        assert succeeded_txs[0].status == PaymentStatus.SUCCEEDED

        # Query FAILED transactions -> 0
        failed_txs = services.ledger_service.list_transactions(status=PaymentStatus.FAILED)
        assert len(failed_txs) == 0
