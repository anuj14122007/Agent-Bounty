"""Central task orchestration service enforcing state machines, delegation, and verification."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, NamedTuple
from sqlalchemy.orm import Session

from agentbounty.agents.manager import ManagerAgent
from agentbounty.agents.registry import AgentRegistry
from agentbounty.config.settings import Settings, get_settings
from agentbounty.domain.enums import (
    BountyStatus,
    SenderType,
    TaskStatus,
    VerificationStatus,
)
from agentbounty.domain.money import Money
from agentbounty.domain.schemas import (
    BountyRead,
    TaskRead,
    VerificationRead,
    WorkerResultRead,
)
from agentbounty.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    InvalidStateTransitionError,
    VerificationEngineError,
    WorkerExecutionError,
)
from agentbounty.persistence.repositories import (
    AuditEventRepository,
    BountyRepository,
    TaskRepository,
    VerificationRepository,
    WorkerResultRepository,
)
from agentbounty.services.agent_communication import AgentCommunicationService
from agentbounty.services.verification import VerificationEngine


# Valid Task lifecycle transitions (from_status -> allowed to_statuses)
_ALLOWED_TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.DRAFT: {TaskStatus.OPEN, TaskStatus.CANCELLED},
    TaskStatus.OPEN: {TaskStatus.ASSIGNED, TaskStatus.CANCELLED},
    TaskStatus.ASSIGNED: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {TaskStatus.SUBMITTED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.SUBMITTED: {TaskStatus.IN_REVIEW, TaskStatus.CANCELLED},
    TaskStatus.IN_REVIEW: {TaskStatus.APPROVED, TaskStatus.REJECTED, TaskStatus.IN_REVIEW},
    TaskStatus.APPROVED: {TaskStatus.AWAITING_AUTHORIZATION},
    TaskStatus.AWAITING_AUTHORIZATION: {TaskStatus.PAYMENT_PENDING, TaskStatus.REJECTED},
    TaskStatus.PAYMENT_PENDING: {TaskStatus.COMPLETED, TaskStatus.FAILED},
    TaskStatus.REJECTED: set(),
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}

# Valid Bounty lifecycle transitions
_ALLOWED_BOUNTY_TRANSITIONS: dict[BountyStatus, set[BountyStatus]] = {
    BountyStatus.OPEN: {BountyStatus.RESERVED, BountyStatus.CANCELLED},
    BountyStatus.RESERVED: {BountyStatus.AWARDED, BountyStatus.CANCELLED},
    BountyStatus.AWARDED: {BountyStatus.PAYMENT_PENDING, BountyStatus.CANCELLED},
    BountyStatus.PAYMENT_PENDING: {BountyStatus.PAID, BountyStatus.CANCELLED},
    BountyStatus.PAID: set(),
    BountyStatus.CANCELLED: set(),
}


class WorkflowExecutionResult(NamedTuple):
    """Aggregate result from executing a complete autonomous workflow."""

    task: TaskRead
    bounty: BountyRead
    worker_result: WorkerResultRead
    verification: VerificationRead
    correlation_id: str


class TaskOrchestrationService:
    """Central orchestration service coordinating marketplace workflow stages."""

    def __init__(
        self,
        session: Session,
        registry: AgentRegistry | None = None,
        manager: ManagerAgent | None = None,
        verification_engine: VerificationEngine | None = None,
        communication_service: AgentCommunicationService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.registry = registry or AgentRegistry()
        self.manager = manager or ManagerAgent(registry=self.registry, settings=self.settings)
        self.verification_engine = verification_engine or VerificationEngine()
        self.communication = communication_service or AgentCommunicationService(session)

        # Repositories
        self.task_repo = TaskRepository(session)
        self.bounty_repo = BountyRepository(session)
        self.worker_result_repo = WorkerResultRepository(session)
        self.verification_repo = VerificationRepository(session)
        self.audit_repo = AuditEventRepository(session)

    # --- State Transition Guards ---

    def _validate_task_transition(self, current_status: TaskStatus, target_status: TaskStatus, task_id: str) -> None:
        """Enforce valid task state machine transitions."""
        allowed = _ALLOWED_TASK_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise InvalidStateTransitionError(
                f"Illegal task state transition for '{task_id}': cannot move from {current_status.value} to {target_status.value}. "
                f"Allowed target states: {[s.value for s in allowed]}."
            )

    def _validate_bounty_transition(
        self, current_status: BountyStatus, target_status: BountyStatus, bounty_id: str
    ) -> None:
        """Enforce valid bounty state machine transitions."""
        allowed = _ALLOWED_BOUNTY_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise InvalidStateTransitionError(
                f"Illegal bounty state transition for '{bounty_id}': cannot move from {current_status.value} to {target_status.value}. "
                f"Allowed target states: {[s.value for s in allowed]}."
            )

    # --- Step 1: Task Creation ---

    def create_task(
        self,
        title: str,
        description: str,
        acceptance_criteria: list[str],
        created_by: str,
        deadline: datetime | None = None,
        correlation_id: str | None = None,
    ) -> TaskRead:
        """Create a new task in DRAFT state."""
        corr_id = correlation_id or str(uuid.uuid4())

        task = self.task_repo.create(
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria,
            created_by=created_by,
            deadline=deadline,
        )

        self.audit_repo.append(
            entity_type="task",
            entity_id=task.id,
            event_type="TASK_CREATED",
            actor_type="USER",
            actor_id=created_by,
            payload={
                "title": title,
                "criteria_count": len(acceptance_criteria),
                "status": task.status.value,
            },
            correlation_id=corr_id,
        )

        self.communication.notify_task_received(task_id=task.id, created_by=created_by, title=title)
        self.session.flush()
        return TaskRead.model_validate(task)

    # --- Step 2: Open Task ---

    def open_task(self, task_id: str, correlation_id: str | None = None) -> TaskRead:
        """Transition a task from DRAFT to OPEN state."""
        corr_id = correlation_id or str(uuid.uuid4())
        task = self.task_repo.get_by_id_or_raise(task_id)

        self._validate_task_transition(task.status, TaskStatus.OPEN, task.id)
        self.task_repo.update_status(task.id, TaskStatus.OPEN)

        self.audit_repo.append(
            entity_type="task",
            entity_id=task.id,
            event_type="TASK_OPENED",
            actor_type="SYSTEM",
            actor_id="orchestrator",
            payload={"status": TaskStatus.OPEN.value},
            correlation_id=corr_id,
        )
        self.session.flush()
        return TaskRead.model_validate(task)

    # --- Step 3: Worker Delegation & Bounty Allocation ---

    def delegate_task(
        self,
        task_id: str,
        proposed_bounty: Decimal | Money | None = None,
        explicit_capabilities: list[str] | None = None,
        correlation_id: str | None = None,
    ) -> tuple[TaskRead, BountyRead]:
        """Manager analyzes task, selects best worker, allocates bounty, and delegates."""
        corr_id = correlation_id or str(uuid.uuid4())
        task = self.task_repo.get_by_id_or_raise(task_id)

        self._validate_task_transition(task.status, TaskStatus.ASSIGNED, task.id)

        # Prevent duplicate delegation
        if task.assigned_agent_id is not None:
            raise DuplicateEntityError(
                f"Task '{task.id}' is already assigned to worker '{task.assigned_agent_id}'."
            )

        task_schema = TaskRead.model_validate(task)

        # 1. Manager analyzes task
        analysis = self.manager.analyze_task(task_schema, explicit_capabilities=explicit_capabilities)
        self.communication.notify_task_analysis(
            task_id=task.id,
            manager_id=self.manager.id,
            required_capabilities=analysis.required_capabilities,
            analysis_notes=analysis.analysis_notes,
        )

        # 2. Manager selects worker
        selected_worker, match_info, explanation = self.manager.select_worker(
            task_schema, required_capabilities=analysis.required_capabilities
        )

        self.communication.notify_worker_selected(
            task_id=task.id,
            manager_id=self.manager.id,
            worker_id=selected_worker.id,
            explanation=explanation,
        )

        self.audit_repo.append(
            entity_type="task",
            entity_id=task.id,
            event_type="WORKER_SELECTED",
            actor_type="MANAGER",
            actor_id=self.manager.id,
            payload={
                "selected_worker_id": selected_worker.id,
                "selected_worker_name": selected_worker.name,
                "match_score": match_info.match_score,
                "matched_capabilities": match_info.matched_capabilities,
            },
            correlation_id=corr_id,
        )

        # 3. Manager calculates and allocates bounty
        bounty_money = self.manager.calculate_bounty(task_schema, proposed_amount=proposed_bounty)
        bounty = self.bounty_repo.create(
            task_id=task.id,
            amount_minor_units=bounty_money.minor_units,
            currency=bounty_money.currency,
        )

        # Transition bounty to RESERVED
        self._validate_bounty_transition(bounty.status, BountyStatus.RESERVED, bounty.id)
        self.bounty_repo.update_status(bounty.id, BountyStatus.RESERVED)

        self.audit_repo.append(
            entity_type="bounty",
            entity_id=bounty.id,
            event_type="BOUNTY_ASSIGNED",
            actor_type="MANAGER",
            actor_id=self.manager.id,
            payload={
                "amount_minor_units": bounty.amount,
                "currency": bounty.currency,
                "status": BountyStatus.RESERVED.value,
            },
            correlation_id=corr_id,
        )

        # 4. Assign task to worker
        self.task_repo.assign_agent(task.id, selected_worker.id)

        self.communication.notify_task_delegated(
            task_id=task.id,
            manager_id=self.manager.id,
            worker_id=selected_worker.id,
            bounty_amount_str=str(bounty_money),
        )

        self.audit_repo.append(
            entity_type="task",
            entity_id=task.id,
            event_type="TASK_DELEGATED",
            actor_type="MANAGER",
            actor_id=self.manager.id,
            payload={
                "assigned_agent_id": selected_worker.id,
                "bounty_id": bounty.id,
                "status": TaskStatus.ASSIGNED.value,
            },
            correlation_id=corr_id,
        )

        self.session.flush()
        return TaskRead.model_validate(task), BountyRead.model_validate(bounty)

    # --- Step 4: Worker Execution & Deliverable Submission ---

    def execute_worker(
        self,
        task_id: str,
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> WorkerResultRead:
        """Execute the assigned worker and persist the submitted deliverable."""
        corr_id = correlation_id or str(uuid.uuid4())
        task = self.task_repo.get_by_id_or_raise(task_id)

        self._validate_task_transition(task.status, TaskStatus.IN_PROGRESS, task.id)

        if not task.assigned_agent_id:
            raise EntityNotFoundError(f"Task '{task.id}' cannot be executed: No worker has been assigned.")

        worker = self.registry.get_worker_or_raise(task.assigned_agent_id)

        # Transition to IN_PROGRESS
        self.task_repo.update_status(task.id, TaskStatus.IN_PROGRESS)
        self.communication.notify_work_started(task_id=task.id, worker_id=worker.id)

        self.audit_repo.append(
            entity_type="task",
            entity_id=task.id,
            event_type="WORK_STARTED",
            actor_type="WORKER",
            actor_id=worker.id,
            payload={"status": TaskStatus.IN_PROGRESS.value},
            correlation_id=corr_id,
        )

        # Determine next submission version
        existing_results = self.worker_result_repo.list_by_task(task.id)
        submission_version = len(existing_results) + 1

        task_schema = TaskRead.model_validate(task)
        exec_result = worker.execute(
            task=task_schema,
            context=context or {},
            submission_version=submission_version,
        )

        # Persist WorkerResult
        worker_result = self.worker_result_repo.create(
            task_id=task.id,
            worker_agent_id=worker.id,
            content=exec_result.content,
            artifact_metadata=exec_result.artifact_metadata,
            submission_version=submission_version,
        )

        # Transition task to SUBMITTED
        self._validate_task_transition(task.status, TaskStatus.SUBMITTED, task.id)
        self.task_repo.update_status(task.id, TaskStatus.SUBMITTED)

        self.communication.notify_result_submitted(
            task_id=task.id,
            worker_id=worker.id,
            submission_version=submission_version,
            content_preview=worker_result.content,
        )

        self.audit_repo.append(
            entity_type="worker_result",
            entity_id=worker_result.id,
            event_type="RESULT_SUBMITTED",
            actor_type="WORKER",
            actor_id=worker.id,
            payload={
                "submission_version": submission_version,
                "content_length": len(worker_result.content),
                "task_status": TaskStatus.SUBMITTED.value,
            },
            correlation_id=corr_id,
        )

        self.session.flush()
        return WorkerResultRead.model_validate(worker_result)

    # --- Step 5: Independent Verification & Outcome Processing ---

    def verify_task(
        self,
        task_id: str,
        worker_result_id: str | None = None,
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> tuple[TaskRead, VerificationRead]:
        """Independently evaluate submitted deliverable against acceptance criteria."""
        corr_id = correlation_id or str(uuid.uuid4())
        task = self.task_repo.get_by_id_or_raise(task_id)

        self._validate_task_transition(task.status, TaskStatus.IN_REVIEW, task.id)

        # Retrieve target worker result
        if worker_result_id:
            worker_result = self.worker_result_repo.get_by_id(worker_result_id)
            if not worker_result or worker_result.task_id != task.id:
                raise EntityNotFoundError(f"WorkerResult '{worker_result_id}' not found for task '{task.id}'.")
        else:
            results = self.worker_result_repo.list_by_task(task.id)
            if not results:
                raise VerificationEngineError(f"Cannot verify task '{task.id}': No worker deliverable found.")
            worker_result = results[-1]  # Latest submission

        # Transition task to IN_REVIEW
        self.task_repo.update_status(task.id, TaskStatus.IN_REVIEW)

        self.communication.notify_verification_started(
            task_id=task.id,
            worker_result_id=worker_result.id,
            criteria_count=len(task.acceptance_criteria),
        )

        self.audit_repo.append(
            entity_type="task",
            entity_id=task.id,
            event_type="VERIFICATION_STARTED",
            actor_type="SYSTEM",
            actor_id="verification_engine",
            payload={
                "worker_result_id": worker_result.id,
                "criteria_count": len(task.acceptance_criteria),
            },
            correlation_id=corr_id,
        )

        # Run independent verification
        task_schema = TaskRead.model_validate(task)
        result_schema = WorkerResultRead.model_validate(worker_result)

        eval_result = self.verification_engine.verify(
            task=task_schema,
            worker_result=result_schema,
            context=context or {},
        )

        # Persist verification record
        verification = self.verification_repo.create(
            worker_result_id=worker_result.id,
            status=eval_result.status,
            score=eval_result.score,
            passed_criteria=eval_result.passed_criteria,
            failed_criteria=eval_result.failed_criteria,
            explanation=eval_result.explanation,
            verifier_type=eval_result.verifier_type,
        )

        self.communication.notify_verification_completed(
            task_id=task.id,
            worker_result_id=worker_result.id,
            status=verification.status.value,
            score=verification.score,
            explanation=verification.explanation,
        )

        self.audit_repo.append(
            entity_type="verification",
            entity_id=verification.id,
            event_type="VERIFICATION_COMPLETED",
            actor_type="SYSTEM",
            actor_id="verification_engine",
            payload={
                "status": verification.status.value,
                "score": verification.score,
                "passed_count": len(verification.passed_criteria),
                "failed_count": len(verification.failed_criteria),
            },
            correlation_id=corr_id,
        )

        # Process verification outcome
        bounty = self.bounty_repo.get_by_task_id(task.id)

        if verification.status == VerificationStatus.PASSED:
            # Transition IN_REVIEW -> APPROVED -> AWAITING_AUTHORIZATION
            self._validate_task_transition(task.status, TaskStatus.APPROVED, task.id)
            self.task_repo.update_status(task.id, TaskStatus.APPROVED)

            self._validate_task_transition(task.status, TaskStatus.AWAITING_AUTHORIZATION, task.id)
            self.task_repo.update_status(task.id, TaskStatus.AWAITING_AUTHORIZATION)

            if bounty:
                self._validate_bounty_transition(bounty.status, BountyStatus.AWARDED, bounty.id)
                self.bounty_repo.update_status(bounty.id, BountyStatus.AWARDED)
                self.audit_repo.append(
                    entity_type="bounty",
                    entity_id=bounty.id,
                    event_type="BOUNTY_AWARDED",
                    actor_type="SYSTEM",
                    actor_id="orchestrator",
                    payload={
                        "amount_minor_units": bounty.amount,
                        "currency": bounty.currency,
                        "status": BountyStatus.AWARDED.value,
                    },
                    correlation_id=corr_id,
                )

            self.audit_repo.append(
                entity_type="task",
                entity_id=task.id,
                event_type="TASK_APPROVED",
                actor_type="SYSTEM",
                actor_id="orchestrator",
                payload={"status": TaskStatus.APPROVED.value},
                correlation_id=corr_id,
            )

            self.audit_repo.append(
                entity_type="task",
                entity_id=task.id,
                event_type="TASK_AWAITING_AUTHORIZATION",
                actor_type="SYSTEM",
                actor_id="orchestrator",
                payload={"status": TaskStatus.AWAITING_AUTHORIZATION.value},
                correlation_id=corr_id,
            )

        elif verification.status == VerificationStatus.FAILED:
            # Transition IN_REVIEW -> REJECTED
            self._validate_task_transition(task.status, TaskStatus.REJECTED, task.id)
            self.task_repo.update_status(task.id, TaskStatus.REJECTED)

            if bounty:
                self._validate_bounty_transition(bounty.status, BountyStatus.CANCELLED, bounty.id)
                self.bounty_repo.update_status(bounty.id, BountyStatus.CANCELLED)
                self.audit_repo.append(
                    entity_type="bounty",
                    entity_id=bounty.id,
                    event_type="BOUNTY_CANCELLED",
                    actor_type="SYSTEM",
                    actor_id="orchestrator",
                    payload={
                        "amount_minor_units": bounty.amount,
                        "currency": bounty.currency,
                        "status": BountyStatus.CANCELLED.value,
                    },
                    correlation_id=corr_id,
                )

            self.audit_repo.append(
                entity_type="task",
                entity_id=task.id,
                event_type="TASK_REJECTED",
                actor_type="SYSTEM",
                actor_id="orchestrator",
                payload={
                    "status": TaskStatus.REJECTED.value,
                    "reason": "Verification criteria failed.",
                },
                correlation_id=corr_id,
            )

        elif verification.status == VerificationStatus.NEEDS_HUMAN_REVIEW:
            # Remains in IN_REVIEW, awaiting manual human review. Never auto-approved.
            self.audit_repo.append(
                entity_type="task",
                entity_id=task.id,
                event_type="TASK_HELD_FOR_HUMAN_REVIEW",
                actor_type="SYSTEM",
                actor_id="orchestrator",
                payload={
                    "status": task.status.value,
                    "reason": "Ambiguous or subjective criteria require human judgment.",
                },
                correlation_id=corr_id,
            )

        self.session.flush()
        return TaskRead.model_validate(task), VerificationRead.model_validate(verification)

    # --- End-to-End Autonomous Workflow Execution ---

    def run_full_workflow(
        self,
        title: str,
        description: str,
        acceptance_criteria: list[str],
        created_by: str,
        proposed_bounty: Decimal | Money | None = None,
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> WorkflowExecutionResult:
        """Run the end-to-end workflow from submission to verified outcome."""
        corr_id = correlation_id or str(uuid.uuid4())

        try:
            # 1. Human creates task (DRAFT)
            task = self.create_task(
                title=title,
                description=description,
                acceptance_criteria=acceptance_criteria,
                created_by=created_by,
                correlation_id=corr_id,
            )

            # 2. Marketplace opens task (OPEN)
            task = self.open_task(task_id=task.id, correlation_id=corr_id)

            # 3. Manager delegates task to specialist worker (ASSIGNED) & reserves bounty
            task, bounty = self.delegate_task(
                task_id=task.id,
                proposed_bounty=proposed_bounty,
                correlation_id=corr_id,
            )

            # 4. Worker executes task & submits deliverable (SUBMITTED)
            worker_result = self.execute_worker(
                task_id=task.id,
                context=context,
                correlation_id=corr_id,
            )

            # 5. Independent verification evaluates criteria
            task, verification = self.verify_task(
                task_id=task.id,
                worker_result_id=worker_result.id,
                context=context,
                correlation_id=corr_id,
            )

            # Retrieve updated bounty reflecting verification outcome
            bounty_record = self.bounty_repo.get_by_task_id(task.id)
            final_bounty = (
                BountyRead.model_validate(bounty_record)
                if bounty_record
                else bounty
            )

            return WorkflowExecutionResult(
                task=task,
                bounty=final_bounty,
                worker_result=worker_result,
                verification=verification,
                correlation_id=corr_id,
            )

        except Exception as err:
            # Ensure workflow failure is recorded in audit trail
            self.session.rollback()
            try:
                self.audit_repo.append(
                    entity_type="workflow",
                    entity_id=task_id if "task" in locals() and task else "unknown",
                    event_type="WORKFLOW_FAILED",
                    actor_type="SYSTEM",
                    actor_id="orchestrator",
                    payload={"error": str(err), "error_type": type(err).__name__},
                    correlation_id=corr_id,
                )
                self.session.flush()
            except Exception:
                pass
            raise
