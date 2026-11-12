"""Integration and end-to-end tests for TaskOrchestrationService."""

from __future__ import annotations

from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from agentbounty.agents.profiles import DATA_ANALYST_PROFILE
from agentbounty.agents.registry import AgentRegistry
from agentbounty.config.settings import Settings
from agentbounty.domain.enums import (
    BountyStatus,
    TaskStatus,
    VerificationStatus,
)
from agentbounty.exceptions import (
    BountyLimitExceededError,
    InvalidStateTransitionError,
    NoEligibleWorkerError,
)
from agentbounty.persistence.models import Bounty, Task
from agentbounty.persistence.repositories import (
    AgentMessageRepository,
    AuditEventRepository,
    BountyRepository,
    TaskRepository,
)
from agentbounty.services.task_orchestration import TaskOrchestrationService


class TestTaskOrchestrationService:
    """Integration tests for task orchestration, state machines, and end-to-end lifecycles."""

    def test_full_successful_workflow(self, session: Session, test_settings: Settings) -> None:
        registry = AgentRegistry()
        registry.sync_with_db(session)

        orchestrator = TaskOrchestrationService(
            session=session,
            registry=registry,
            settings=test_settings,
        )

        res = orchestrator.run_full_workflow(
            title="Create Professional Product Overview",
            description="Please write a structured 300-word introduction for AgentBounty.",
            acceptance_criteria=[
                "contains:AgentBounty",
                "has_section:Introduction",
                "min_words:20",
            ],
            created_by="alice_founder",
            proposed_bounty=Decimal("3.50"),
        )

        # 1. Verify Task final state
        assert res.task.status == TaskStatus.AWAITING_AUTHORIZATION
        assert res.task.assigned_agent_id is not None

        # 2. Verify Bounty final state
        assert res.bounty.amount == 350  # $3.50 in cents
        assert res.bounty.status == BountyStatus.AWARDED

        # 3. Verify Worker Deliverable
        assert res.worker_result.submission_version == 1
        assert "AgentBounty" in res.worker_result.content
        assert len(res.worker_result.content.split()) >= 20

        # 4. Verify Independent Verification
        assert res.verification.status == VerificationStatus.PASSED
        assert res.verification.score == 100
        assert len(res.verification.passed_criteria) == 3
        assert len(res.verification.failed_criteria) == 0

        # 5. Verify Persistent Communication Messages
        msg_repo = AgentMessageRepository(session)
        messages = msg_repo.list_by_task(res.task.id)
        msg_types = [m.message_type for m in messages]
        assert "TASK_RECEIVED" in msg_types
        assert "TASK_ANALYSIS" in msg_types
        assert "WORKER_SELECTED" in msg_types
        assert "TASK_DELEGATED" in msg_types
        assert "WORK_STARTED" in msg_types
        assert "RESULT_SUBMITTED" in msg_types
        assert "VERIFICATION_STARTED" in msg_types
        assert "VERIFICATION_COMPLETED" in msg_types

        # 6. Verify Immutable Audit Events
        audit_repo = AuditEventRepository(session)
        audit_events = audit_repo.list_by_correlation_id(res.correlation_id)
        assert len(audit_events) >= 8
        event_types = [e.event_type for e in audit_events]
        assert "TASK_CREATED" in event_types
        assert "TASK_OPENED" in event_types
        assert "WORKER_SELECTED" in event_types
        assert "BOUNTY_ASSIGNED" in event_types
        assert "TASK_DELEGATED" in event_types
        assert "WORK_STARTED" in event_types
        assert "RESULT_SUBMITTED" in event_types
        assert "VERIFICATION_STARTED" in event_types
        assert "VERIFICATION_COMPLETED" in event_types
        assert "TASK_APPROVED" in event_types
        assert "TASK_AWAITING_AUTHORIZATION" in event_types

    def test_workflow_with_failing_criterion_reaches_rejected(
        self, session: Session, test_settings: Settings
    ) -> None:
        registry = AgentRegistry()
        registry.sync_with_db(session)

        orchestrator = TaskOrchestrationService(
            session=session,
            registry=registry,
            settings=test_settings,
        )

        res = orchestrator.run_full_workflow(
            title="Write Product Intro",
            description="Write a short summary.",
            acceptance_criteria=[
                "contains:ImpossiblePhraseThatDoesNotExistInDemoOutput12345",
            ],
            created_by="bob_creator",
            proposed_bounty=Decimal("2.00"),
        )

        assert res.verification.status == VerificationStatus.FAILED
        assert res.task.status == TaskStatus.REJECTED
        assert res.bounty.status == BountyStatus.CANCELLED

        audit_repo = AuditEventRepository(session)
        audit_events = audit_repo.list_by_correlation_id(res.correlation_id)
        event_types = [e.event_type for e in audit_events]
        assert "TASK_REJECTED" in event_types

    def test_workflow_with_ambiguous_criterion_held_for_human_review(
        self, session: Session, test_settings: Settings
    ) -> None:
        registry = AgentRegistry()
        registry.sync_with_db(session)

        orchestrator = TaskOrchestrationService(
            session=session,
            registry=registry,
            settings=test_settings,
        )

        res = orchestrator.run_full_workflow(
            title="Write Creative Brand Manifesto",
            description="Please write an introduction.",
            acceptance_criteria=[
                "contains:Introduction",
                "The piece must sound deeply soulful and avant-garde",
            ],
            created_by="carol_founder",
            proposed_bounty=Decimal("1.50"),
        )

        # Status must remain in IN_REVIEW pending human authorization
        assert res.verification.status == VerificationStatus.NEEDS_HUMAN_REVIEW
        assert res.task.status == TaskStatus.IN_REVIEW
        assert res.bounty.status == BountyStatus.RESERVED

        audit_repo = AuditEventRepository(session)
        audit_events = audit_repo.list_by_correlation_id(res.correlation_id)
        event_types = [e.event_type for e in audit_events]
        assert "TASK_HELD_FOR_HUMAN_REVIEW" in event_types

    def test_invalid_state_transition_rejected(self, session: Session, test_settings: Settings) -> None:
        registry = AgentRegistry()
        registry.sync_with_db(session)

        orchestrator = TaskOrchestrationService(
            session=session,
            registry=registry,
            settings=test_settings,
        )

        # Create task (DRAFT)
        task = orchestrator.create_task(
            title="Draft Task",
            description="Testing invalid transitions.",
            acceptance_criteria=["min_words:5"],
            created_by="tester",
        )

        # Illegal: DRAFT -> ASSIGNED directly without opening
        with pytest.raises(InvalidStateTransitionError, match="Illegal task state transition"):
            orchestrator.delegate_task(task.id)

    def test_bounty_ceiling_exceeded_rejected(self, session: Session, test_settings: Settings) -> None:
        registry = AgentRegistry()
        registry.sync_with_db(session)

        orchestrator = TaskOrchestrationService(
            session=session,
            registry=registry,
            settings=test_settings,
        )

        task = orchestrator.create_task(
            title="Write Blog Post",
            description="Please write a post.",
            acceptance_criteria=["min_words:10"],
            created_by="tester",
        )
        orchestrator.open_task(task.id)

        # Proposed bounty exceeds $5.00 limit
        with pytest.raises(BountyLimitExceededError, match="exceeds configured maximum limit"):
            orchestrator.delegate_task(task.id, proposed_bounty=Decimal("25.00"))

    def test_duplicate_delegation_prevented(self, session: Session, test_settings: Settings) -> None:
        registry = AgentRegistry()
        registry.sync_with_db(session)

        orchestrator = TaskOrchestrationService(
            session=session,
            registry=registry,
            settings=test_settings,
        )

        task = orchestrator.create_task(
            title="Write Blog Post",
            description="Please write a post.",
            acceptance_criteria=["min_words:10"],
            created_by="tester",
        )
        orchestrator.open_task(task.id)
        orchestrator.delegate_task(task.id, proposed_bounty=Decimal("2.00"))

        # Second delegation attempt must fail
        with pytest.raises(InvalidStateTransitionError):
            orchestrator.delegate_task(task.id, proposed_bounty=Decimal("2.00"))

    def test_data_analyst_end_to_end_workflow(self, session: Session, test_settings: Settings) -> None:
        registry = AgentRegistry()
        registry.sync_with_db(session)

        orchestrator = TaskOrchestrationService(
            session=session,
            registry=registry,
            settings=test_settings,
        )

        res = orchestrator.run_full_workflow(
            title="Calculate Financial Sample Statistics",
            description="Analyze quantitative dataset metrics: 100, 200, 300, 400",
            acceptance_criteria=[
                "contains:Arithmetic Mean",
                "has_section:Tabular Summary",
            ],
            created_by="finance_lead",
            context={"data": [100, 200, 300, 400]},
        )

        assert res.task.assigned_agent_id == registry.get_worker_or_raise(DATA_ANALYST_PROFILE.id).id
        assert res.verification.status == VerificationStatus.PASSED
        assert "Arithmetic Mean" in res.worker_result.content
        assert res.task.status == TaskStatus.AWAITING_AUTHORIZATION

    def test_code_assistant_end_to_end_workflow(self, session: Session, test_settings: Settings) -> None:
        registry = AgentRegistry()
        registry.sync_with_db(session)

        orchestrator = TaskOrchestrationService(
            session=session,
            registry=registry,
            settings=test_settings,
        )

        res = orchestrator.run_full_workflow(
            title="Draft Python Validator",
            description="Create a python function to validate input schemas.",
            acceptance_criteria=[
                "contains:def",
                "has_section:Architecture Overview",
            ],
            created_by="tech_lead",
        )

        assert res.verification.status == VerificationStatus.PASSED
        assert "```python" in res.worker_result.content
        assert res.task.status == TaskStatus.AWAITING_AUTHORIZATION

    def test_regression_successful_verification_updates_bounty_in_db_and_emits_audit(
        self, session: Session, test_settings: Settings
    ) -> None:
        registry = AgentRegistry()
        registry.sync_with_db(session)
        orchestrator = TaskOrchestrationService(
            session=session,
            registry=registry,
            settings=test_settings,
        )

        res = orchestrator.run_full_workflow(
            title="Create Professional Overview",
            description="Please write a structured 300-word introduction for AgentBounty.",
            acceptance_criteria=[
                "contains:AgentBounty",
                "has_section:Introduction",
                "min_words:20",
            ],
            created_by="alice_founder",
            proposed_bounty=Decimal("4.00"),
        )

        # 1. Schema outputs
        assert res.verification.status == VerificationStatus.PASSED
        assert res.task.status == TaskStatus.AWAITING_AUTHORIZATION
        assert res.bounty.status == BountyStatus.AWARDED
        assert res.bounty.amount == 400

        # 2. Database records consistency
        db_bounty = session.get(Bounty, res.bounty.id)
        assert db_bounty is not None
        assert db_bounty.status == BountyStatus.AWARDED
        assert db_bounty.amount == 400

        db_task = session.get(Task, res.task.id)
        assert db_task is not None
        assert db_task.status == TaskStatus.AWAITING_AUTHORIZATION

        # 3. Audit trail records BOUNTY_AWARDED
        audit_repo = AuditEventRepository(session)
        audit_events = audit_repo.list_by_correlation_id(res.correlation_id)
        event_types = [e.event_type for e in audit_events]
        assert "BOUNTY_AWARDED" in event_types
        assert "TASK_APPROVED" in event_types
        assert "TASK_AWAITING_AUTHORIZATION" in event_types

    def test_regression_failed_verification_cancels_bounty_in_db_and_emits_audit(
        self, session: Session, test_settings: Settings
    ) -> None:
        registry = AgentRegistry()
        registry.sync_with_db(session)
        orchestrator = TaskOrchestrationService(
            session=session,
            registry=registry,
            settings=test_settings,
        )

        res = orchestrator.run_full_workflow(
            title="Write Product Intro",
            description="Write a short summary.",
            acceptance_criteria=[
                "contains:NonExistentToken9999",
            ],
            created_by="bob_creator",
            proposed_bounty=Decimal("2.50"),
        )

        # 1. Schema outputs
        assert res.verification.status == VerificationStatus.FAILED
        assert res.task.status == TaskStatus.REJECTED
        assert res.bounty.status == BountyStatus.CANCELLED
        assert res.bounty.amount == 250

        # 2. Database records consistency
        db_bounty = session.get(Bounty, res.bounty.id)
        assert db_bounty is not None
        assert db_bounty.status == BountyStatus.CANCELLED

        db_task = session.get(Task, res.task.id)
        assert db_task is not None
        assert db_task.status == TaskStatus.REJECTED

        # 3. Audit trail records BOUNTY_CANCELLED
        audit_repo = AuditEventRepository(session)
        audit_events = audit_repo.list_by_correlation_id(res.correlation_id)
        event_types = [e.event_type for e in audit_events]
        assert "BOUNTY_CANCELLED" in event_types
        assert "TASK_REJECTED" in event_types

    def test_regression_human_review_holds_task_and_bounty_reserved_in_db(
        self, session: Session, test_settings: Settings
    ) -> None:
        registry = AgentRegistry()
        registry.sync_with_db(session)
        orchestrator = TaskOrchestrationService(
            session=session,
            registry=registry,
            settings=test_settings,
        )

        res = orchestrator.run_full_workflow(
            title="Write Creative Brand Manifesto",
            description="Please write an introduction.",
            acceptance_criteria=[
                "contains:Introduction",
                "The tone must be exquisitely evocative and poetic",
            ],
            created_by="carol_founder",
            proposed_bounty=Decimal("1.50"),
        )

        # 1. Schema outputs
        assert res.verification.status == VerificationStatus.NEEDS_HUMAN_REVIEW
        assert res.task.status == TaskStatus.IN_REVIEW
        assert res.bounty.status == BountyStatus.RESERVED

        # 2. Database records consistency
        db_bounty = session.get(Bounty, res.bounty.id)
        assert db_bounty is not None
        assert db_bounty.status == BountyStatus.RESERVED

        db_task = session.get(Task, res.task.id)
        assert db_task is not None
        assert db_task.status == TaskStatus.IN_REVIEW

        # 3. Audit trail records TASK_HELD_FOR_HUMAN_REVIEW and no premature award/cancellation
        audit_repo = AuditEventRepository(session)
        audit_events = audit_repo.list_by_correlation_id(res.correlation_id)
        event_types = [e.event_type for e in audit_events]
        assert "TASK_HELD_FOR_HUMAN_REVIEW" in event_types
        assert "BOUNTY_AWARDED" not in event_types
        assert "BOUNTY_CANCELLED" not in event_types

    def test_regression_repeated_verification_after_passed_rejected(
        self, session: Session, test_settings: Settings
    ) -> None:
        registry = AgentRegistry()
        registry.sync_with_db(session)
        orchestrator = TaskOrchestrationService(
            session=session,
            registry=registry,
            settings=test_settings,
        )

        res = orchestrator.run_full_workflow(
            title="Create Professional Overview",
            description="Please write a structured 300-word introduction for AgentBounty.",
            acceptance_criteria=[
                "contains:AgentBounty",
                "has_section:Introduction",
                "min_words:20",
            ],
            created_by="alice_founder",
            proposed_bounty=Decimal("3.00"),
        )
        assert res.task.status == TaskStatus.AWAITING_AUTHORIZATION
        assert res.bounty.status == BountyStatus.AWARDED

        # Attempt repeated verification
        with pytest.raises(InvalidStateTransitionError, match="Illegal task state transition"):
            orchestrator.verify_task(task_id=res.task.id)

        # Verify state in DB remained consistent and unchanged
        db_task = session.get(Task, res.task.id)
        db_bounty = session.get(Bounty, res.bounty.id)
        assert db_task is not None and db_task.status == TaskStatus.AWAITING_AUTHORIZATION
        assert db_bounty is not None and db_bounty.status == BountyStatus.AWARDED

    def test_regression_repeated_verification_after_failed_rejected(
        self, session: Session, test_settings: Settings
    ) -> None:
        registry = AgentRegistry()
        registry.sync_with_db(session)
        orchestrator = TaskOrchestrationService(
            session=session,
            registry=registry,
            settings=test_settings,
        )

        res = orchestrator.run_full_workflow(
            title="Write Product Intro",
            description="Write a short summary.",
            acceptance_criteria=[
                "contains:NonExistentToken9999",
            ],
            created_by="bob_creator",
            proposed_bounty=Decimal("2.00"),
        )
        assert res.task.status == TaskStatus.REJECTED
        assert res.bounty.status == BountyStatus.CANCELLED

        # Attempt repeated verification
        with pytest.raises(InvalidStateTransitionError, match="Illegal task state transition"):
            orchestrator.verify_task(task_id=res.task.id)

        # Verify state in DB remained consistent and unchanged
        db_task = session.get(Task, res.task.id)
        db_bounty = session.get(Bounty, res.bounty.id)
        assert db_task is not None and db_task.status == TaskStatus.REJECTED
        assert db_bounty is not None and db_bounty.status == BountyStatus.CANCELLED

    def test_regression_step_by_step_verification_lifecycle(
        self, session: Session, test_settings: Settings
    ) -> None:
        """Verify individual lifecycle steps update task and bounty records consistently in DB."""
        registry = AgentRegistry()
        registry.sync_with_db(session)
        orchestrator = TaskOrchestrationService(
            session=session,
            registry=registry,
            settings=test_settings,
        )

        # Step 1: Create task
        task = orchestrator.create_task(
            title="Step by step task",
            description="Write an introduction for AgentBounty with detailed sections.",
            acceptance_criteria=["contains:AgentBounty", "min_words:20"],
            created_by="founder",
        )
        assert task.status == TaskStatus.DRAFT

        # Step 2: Open task
        task = orchestrator.open_task(task.id)
        assert task.status == TaskStatus.OPEN

        # Step 3: Delegate task
        task, bounty = orchestrator.delegate_task(task.id, proposed_bounty=Decimal("3.50"))
        assert task.status == TaskStatus.ASSIGNED
        assert bounty.status == BountyStatus.RESERVED
        db_bounty = session.get(Bounty, bounty.id)
        assert db_bounty is not None and db_bounty.status == BountyStatus.RESERVED

        # Step 4: Execute worker
        worker_result = orchestrator.execute_worker(task.id)
        assert worker_result.submission_version == 1
        db_task = session.get(Task, task.id)
        assert db_task is not None and db_task.status == TaskStatus.SUBMITTED

        # Step 5: Verify task
        task_verified, verification = orchestrator.verify_task(task.id, worker_result.id)
        assert verification.status == VerificationStatus.PASSED
        assert task_verified.status == TaskStatus.AWAITING_AUTHORIZATION

        # Assert bounty in DB was updated to AWARDED
        db_bounty_after = session.get(Bounty, bounty.id)
        assert db_bounty_after is not None
        assert db_bounty_after.status == BountyStatus.AWARDED
