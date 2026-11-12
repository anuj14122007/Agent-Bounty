"""Repository implementations for AgentBounty entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agentbounty.domain.enums import (
    AgentRole,
    AgentStatus,
    AuthorizationDecision,
    BountyStatus,
    PaymentExecutionMode,
    PaymentStatus,
    SenderType,
    TaskStatus,
    VerificationStatus,
    VerifierType,
)
from agentbounty.exceptions import (
    AppendOnlyViolationError,
    DuplicateEntityError,
    EntityNotFoundError,
)
from agentbounty.persistence.base import utc_now
from agentbounty.persistence.models import (
    Agent,
    AgentMessage,
    AuditEvent,
    Bounty,
    PaymentAuthorization,
    PaymentTransaction,
    Task,
    Verification,
    WorkerResult,
)

T = TypeVar("T")


class BaseRepository:
    """Base repository holding an active SQLAlchemy Session."""

    def __init__(self, session: Session) -> None:
        self.session = session


class AgentRepository(BaseRepository):
    """Repository managing Agent records."""

    def create(
        self,
        name: str,
        role: AgentRole,
        description: str,
        capabilities: list[str] | None = None,
        status: AgentStatus = AgentStatus.ACTIVE,
        id: str | None = None,
    ) -> Agent:
        kwargs: dict[str, Any] = {
            "name": name,
            "role": role,
            "description": description,
            "capabilities": capabilities or [],
            "status": status,
        }
        if id is not None:
            kwargs["id"] = id
        agent = Agent(**kwargs)
        self.session.add(agent)
        self.session.flush()
        return agent

    def get_by_id(self, agent_id: str) -> Agent | None:
        return self.session.get(Agent, agent_id)

    def get_by_id_or_raise(self, agent_id: str) -> Agent:
        agent = self.get_by_id(agent_id)
        if not agent:
            raise EntityNotFoundError(f"Agent with ID '{agent_id}' not found.")
        return agent

    def list_all(
        self,
        role: AgentRole | None = None,
        status: AgentStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Agent]:
        stmt = select(Agent)
        if role is not None:
            stmt = stmt.where(Agent.role == role)
        if status is not None:
            stmt = stmt.where(Agent.status == status)
        stmt = stmt.order_by(Agent.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt).all())

    def update_status(self, agent_id: str, new_status: AgentStatus) -> Agent:
        agent = self.get_by_id_or_raise(agent_id)
        agent.status = new_status
        self.session.flush()
        return agent


class TaskRepository(BaseRepository):
    """Repository managing Task records."""

    def create(
        self,
        title: str,
        description: str,
        acceptance_criteria: list[str],
        created_by: str,
        deadline: datetime | None = None,
    ) -> Task:
        task = Task(
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria,
            created_by=created_by,
            deadline=deadline,
            status=TaskStatus.DRAFT,
        )
        self.session.add(task)
        self.session.flush()
        return task

    def get_by_id(self, task_id: str) -> Task | None:
        return self.session.get(Task, task_id)

    def get_by_id_or_raise(self, task_id: str) -> Task:
        task = self.get_by_id(task_id)
        if not task:
            raise EntityNotFoundError(f"Task with ID '{task_id}' not found.")
        return task

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        assigned_agent_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        stmt = select(Task)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if assigned_agent_id is not None:
            stmt = stmt.where(Task.assigned_agent_id == assigned_agent_id)
        stmt = stmt.order_by(Task.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt).all())

    def assign_agent(self, task_id: str, agent_id: str) -> Task:
        task = self.get_by_id_or_raise(task_id)
        task.assigned_agent_id = agent_id
        task.status = TaskStatus.ASSIGNED
        self.session.flush()
        return task

    def update_status(self, task_id: str, new_status: TaskStatus) -> Task:
        task = self.get_by_id_or_raise(task_id)
        task.status = new_status
        self.session.flush()
        return task


class BountyRepository(BaseRepository):
    """Repository managing Bounty allocations.

    Enforces 1:1 relationship with tasks and integer minor units storage.
    """

    def create(
        self,
        task_id: str,
        amount_minor_units: int,
        currency: str = "USD",
    ) -> Bounty:
        existing = self.get_by_task_id(task_id)
        if existing:
            raise DuplicateEntityError(
                f"Task '{task_id}' already has an active or associated bounty ('{existing.id}')."
            )

        bounty = Bounty(
            task_id=task_id,
            amount=amount_minor_units,
            currency=currency.upper(),
            status=BountyStatus.OPEN,
        )
        try:
            self.session.add(bounty)
            self.session.flush()
        except IntegrityError as err:
            self.session.rollback()
            raise DuplicateEntityError(
                f"Cannot create duplicate bounty for task '{task_id}': {err}"
            ) from err
        return bounty

    def get_by_id(self, bounty_id: str) -> Bounty | None:
        return self.session.get(Bounty, bounty_id)

    def get_by_task_id(self, task_id: str) -> Bounty | None:
        stmt = select(Bounty).where(Bounty.task_id == task_id)
        return self.session.scalars(stmt).first()

    def list_bounties(
        self,
        status: BountyStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Bounty]:
        stmt = select(Bounty)
        if status is not None:
            stmt = stmt.where(Bounty.status == status)
        stmt = stmt.order_by(Bounty.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt).all())

    def update_status(self, bounty_id: str, new_status: BountyStatus) -> Bounty:
        bounty = self.session.get(Bounty, bounty_id)
        if not bounty:
            raise EntityNotFoundError(f"Bounty with ID '{bounty_id}' not found.")
        bounty.status = new_status
        self.session.flush()
        return bounty


class AgentMessageRepository(BaseRepository):
    """Repository managing communication messages between participants."""

    def create(
        self,
        task_id: str,
        sender_type: SenderType,
        sender_id: str | None,
        recipient_id: str | None,
        message_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMessage:
        msg = AgentMessage(
            task_id=task_id,
            sender_type=sender_type,
            sender_id=sender_id,
            recipient_id=recipient_id,
            message_type=message_type,
            content=content,
            message_metadata=metadata or {},
        )
        self.session.add(msg)
        self.session.flush()
        return msg

    def get_by_id(self, message_id: str) -> AgentMessage | None:
        return self.session.get(AgentMessage, message_id)

    def list_by_task(
        self,
        task_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentMessage]:
        stmt = (
            select(AgentMessage)
            .where(AgentMessage.task_id == task_id)
            .order_by(AgentMessage.timestamp.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(stmt).all())


class WorkerResultRepository(BaseRepository):
    """Repository managing Worker Agent submitted deliverables."""

    def create(
        self,
        task_id: str,
        worker_agent_id: str,
        content: str,
        artifact_metadata: dict[str, Any] | None = None,
        submission_version: int = 1,
    ) -> WorkerResult:
        result = WorkerResult(
            task_id=task_id,
            worker_agent_id=worker_agent_id,
            content=content,
            artifact_metadata=artifact_metadata or {},
            submission_version=submission_version,
        )
        self.session.add(result)
        self.session.flush()
        return result

    def get_by_id(self, result_id: str) -> WorkerResult | None:
        return self.session.get(WorkerResult, result_id)

    def list_by_task(self, task_id: str) -> list[WorkerResult]:
        stmt = (
            select(WorkerResult)
            .where(WorkerResult.task_id == task_id)
            .order_by(WorkerResult.submission_version.asc())
        )
        return list(self.session.scalars(stmt).all())


class VerificationRepository(BaseRepository):
    """Repository managing verification reports on worker results."""

    def create(
        self,
        worker_result_id: str,
        status: VerificationStatus,
        explanation: str,
        score: int | None = None,
        passed_criteria: list[str] | None = None,
        failed_criteria: list[str] | None = None,
        verifier_type: VerifierType = VerifierType.AUTOMATED,
    ) -> Verification:
        verification = Verification(
            worker_result_id=worker_result_id,
            status=status,
            explanation=explanation,
            score=score,
            passed_criteria=passed_criteria or [],
            failed_criteria=failed_criteria or [],
            verifier_type=verifier_type,
        )
        self.session.add(verification)
        self.session.flush()
        return verification

    def get_by_id(self, verification_id: str) -> Verification | None:
        return self.session.get(Verification, verification_id)

    def list_by_worker_result(self, worker_result_id: str) -> list[Verification]:
        stmt = (
            select(Verification)
            .where(Verification.worker_result_id == worker_result_id)
            .order_by(Verification.verified_at.desc())
        )
        return list(self.session.scalars(stmt).all())


class PaymentAuthorizationRepository(BaseRepository):
    """Repository managing human financial authorizations."""

    def create(
        self,
        task_id: str,
        bounty_id: str,
        authorized_by: str,
        decision: AuthorizationDecision,
        authorized_amount_minor_units: int,
        currency: str = "USD",
        reason: str | None = None,
    ) -> PaymentAuthorization:
        auth = PaymentAuthorization(
            task_id=task_id,
            bounty_id=bounty_id,
            authorized_by=authorized_by,
            decision=decision,
            authorized_amount=authorized_amount_minor_units,
            currency=currency.upper(),
            reason=reason,
        )
        self.session.add(auth)
        self.session.flush()
        return auth

    def get_by_id(self, auth_id: str) -> PaymentAuthorization | None:
        return self.session.get(PaymentAuthorization, auth_id)

    def list_by_task(self, task_id: str) -> list[PaymentAuthorization]:
        stmt = (
            select(PaymentAuthorization)
            .where(PaymentAuthorization.task_id == task_id)
            .order_by(PaymentAuthorization.authorized_at.desc())
        )
        return list(self.session.scalars(stmt).all())


class PaymentTransactionRepository(BaseRepository):
    """Repository managing payment transactions with idempotency protection."""

    def create(
        self,
        task_id: str,
        bounty_id: str,
        provider_name: str,
        execution_mode: PaymentExecutionMode,
        amount_minor_units: int,
        idempotency_key: str,
        authorization_id: str | None = None,
        currency: str = "USD",
        external_reference: str | None = None,
    ) -> PaymentTransaction:
        existing = self.get_by_idempotency_key(idempotency_key)
        if existing:
            raise DuplicateEntityError(
                f"Transaction with idempotency key '{idempotency_key}' already exists ('{existing.id}')."
            )

        if execution_mode == PaymentExecutionMode.SIMULATED and external_reference is not None:
            raise ValueError(
                "Simulated payment transactions cannot contain a fabricated external provider reference."
            )

        tx = PaymentTransaction(
            task_id=task_id,
            bounty_id=bounty_id,
            authorization_id=authorization_id,
            provider_name=provider_name,
            execution_mode=execution_mode,
            amount=amount_minor_units,
            currency=currency.upper(),
            status=PaymentStatus.CREATED,
            idempotency_key=idempotency_key,
            external_reference=external_reference,
        )
        try:
            self.session.add(tx)
            self.session.flush()
        except IntegrityError as err:
            self.session.rollback()
            raise DuplicateEntityError(
                f"Idempotency key violation: '{idempotency_key}' already used: {err}"
            ) from err
        return tx

    def get_by_id(self, tx_id: str) -> PaymentTransaction | None:
        return self.session.get(PaymentTransaction, tx_id)

    def get_by_idempotency_key(self, idempotency_key: str) -> PaymentTransaction | None:
        stmt = select(PaymentTransaction).where(
            PaymentTransaction.idempotency_key == idempotency_key
        )
        return self.session.scalars(stmt).first()

    def list_by_task(self, task_id: str) -> list[PaymentTransaction]:
        stmt = (
            select(PaymentTransaction)
            .where(PaymentTransaction.task_id == task_id)
            .order_by(PaymentTransaction.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def update_status(
        self,
        tx_id: str,
        new_status: PaymentStatus,
        external_reference: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        completed_at: datetime | None = None,
    ) -> PaymentTransaction:
        tx = self.session.get(PaymentTransaction, tx_id)
        if not tx:
            raise EntityNotFoundError(f"Payment transaction with ID '{tx_id}' not found.")

        if tx.execution_mode == PaymentExecutionMode.SIMULATED and external_reference is not None:
            raise ValueError(
                "Simulated payment transactions cannot contain a fabricated external provider reference."
            )

        tx.status = new_status
        if external_reference is not None:
            tx.external_reference = external_reference
        if error_code is not None:
            tx.error_code = error_code
        if error_message is not None:
            tx.error_message = error_message
        if completed_at is not None:
            tx.completed_at = completed_at
        elif new_status in (PaymentStatus.SUCCEEDED, PaymentStatus.FAILED) and not tx.completed_at:
            tx.completed_at = utc_now()

        self.session.flush()
        return tx


class AuditEventRepository(BaseRepository):
    """Append-only repository for audit events.

    STRICT INVARIANT: Audit records can only be created and queried.
    No update or delete operations are exposed.
    """

    def append(
        self,
        entity_type: str,
        entity_id: str,
        event_type: str,
        actor_type: str,
        actor_id: str,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            payload=payload or {},
            correlation_id=correlation_id,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def get_by_id(self, event_id: str) -> AuditEvent | None:
        return self.session.get(AuditEvent, event_id)

    def list_by_entity(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(
                AuditEvent.entity_type == entity_type,
                AuditEvent.entity_id == entity_id,
            )
            .order_by(AuditEvent.timestamp.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(stmt).all())

    def list_by_correlation_id(
        self,
        correlation_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.correlation_id == correlation_id)
            .order_by(AuditEvent.timestamp.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(stmt).all())

    def update(self, *args: Any, **kwargs: Any) -> None:
        """Explicitly disallow updates on audit trail."""
        raise AppendOnlyViolationError("Audit events are immutable and cannot be updated.")

    def delete(self, *args: Any, **kwargs: Any) -> None:
        """Explicitly disallow deletions on audit trail."""
        raise AppendOnlyViolationError("Audit events are immutable and cannot be deleted.")
