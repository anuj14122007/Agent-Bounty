"""SQLAlchemy 2.x persistence models for AgentBounty entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
from agentbounty.persistence.base import Base, TimestampMixin, generate_uuid, utc_now


class Agent(Base, TimestampMixin):
    """An autonomous or semi-autonomous actor (Manager or Worker)."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[AgentRole] = mapped_column(
        SQLEnum(AgentRole, native_enum=False, length=20),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[AgentStatus] = mapped_column(
        SQLEnum(AgentStatus, native_enum=False, length=20),
        nullable=False,
        default=AgentStatus.ACTIVE,
        index=True,
    )

    # Relationships
    assigned_tasks: Mapped[list[Task]] = relationship("Task", back_populates="assigned_agent")
    worker_results: Mapped[list[WorkerResult]] = relationship(
        "WorkerResult", back_populates="worker_agent"
    )


class Task(Base, TimestampMixin):
    """A unit of work submitted by a human for autonomous decomposition and execution."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    assigned_agent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agents.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus, native_enum=False, length=30),
        nullable=False,
        default=TaskStatus.DRAFT,
        index=True,
    )
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    assigned_agent: Mapped[Agent | None] = relationship("Agent", back_populates="assigned_tasks")
    bounty: Mapped[Bounty | None] = relationship("Bounty", back_populates="task", uselist=False)
    messages: Mapped[list[AgentMessage]] = relationship(
        "AgentMessage",
        back_populates="task",
        cascade="all, delete-orphan",
    )
    worker_results: Mapped[list[WorkerResult]] = relationship(
        "WorkerResult", back_populates="task"
    )
    payment_authorizations: Mapped[list[PaymentAuthorization]] = relationship(
        "PaymentAuthorization", back_populates="task"
    )
    payment_transactions: Mapped[list[PaymentTransaction]] = relationship(
        "PaymentTransaction", back_populates="task"
    )


class Bounty(Base, TimestampMixin):
    """Monetary allocation assigned to a task.

    CRITICAL CONSTRAINT: A task has exactly zero or one active bounty (enforced via unique task_id).
    Amount is stored strictly as integer minor units (cents for USD).
    """

    __tablename__ = "bounties"

    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_non_negative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[BountyStatus] = mapped_column(
        SQLEnum(BountyStatus, native_enum=False, length=20),
        nullable=False,
        default=BountyStatus.OPEN,
        index=True,
    )

    # Relationships
    task: Mapped[Task] = relationship("Task", back_populates="bounty")
    payment_authorizations: Mapped[list[PaymentAuthorization]] = relationship(
        "PaymentAuthorization", back_populates="bounty"
    )
    payment_transactions: Mapped[list[PaymentTransaction]] = relationship(
        "PaymentTransaction", back_populates="bounty"
    )


class AgentMessage(Base):
    """Structured communication between marketplace participants (Agents, Humans, System)."""

    __tablename__ = "agent_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sender_type: Mapped[SenderType] = mapped_column(
        SQLEnum(SenderType, native_enum=False, length=20),
        nullable=False,
    )
    sender_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recipient_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )

    # Relationships
    task: Mapped[Task] = relationship("Task", back_populates="messages")


class WorkerResult(Base):
    """Deliverable submitted by a Worker Agent upon completing a delegated task."""

    __tablename__ = "worker_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    worker_agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    submission_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    task: Mapped[Task] = relationship("Task", back_populates="worker_results")
    worker_agent: Mapped[Agent] = relationship("Agent", back_populates="worker_results")
    verifications: Mapped[list[Verification]] = relationship(
        "Verification", back_populates="worker_result"
    )


class Verification(Base):
    """Result of independent verification evaluating a WorkerResult against acceptance criteria."""

    __tablename__ = "verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    worker_result_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("worker_results.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[VerificationStatus] = mapped_column(
        SQLEnum(VerificationStatus, native_enum=False, length=30),
        nullable=False,
        default=VerificationStatus.PENDING,
        index=True,
    )
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed_criteria: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    failed_criteria: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    verifier_type: Mapped[VerifierType] = mapped_column(
        SQLEnum(VerifierType, native_enum=False, length=30),
        nullable=False,
        default=VerifierType.AUTOMATED,
    )
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    worker_result: Mapped[WorkerResult] = relationship(
        "WorkerResult", back_populates="verifications"
    )


class PaymentAuthorization(Base):
    """Explicit human or authorized actor financial authorization record.

    Distinct from a payment execution transaction to maintain an immutable authorization audit trail.
    """

    __tablename__ = "payment_authorizations"

    __table_args__ = (
        CheckConstraint(
            "authorized_amount >= 0",
            name="amount_non_negative",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bounty_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("bounties.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    authorized_by: Mapped[str] = mapped_column(String(100), nullable=False)
    decision: Mapped[AuthorizationDecision] = mapped_column(
        SQLEnum(AuthorizationDecision, native_enum=False, length=20),
        nullable=False,
        index=True,
    )
    authorized_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    authorized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    task: Mapped[Task] = relationship("Task", back_populates="payment_authorizations")
    bounty: Mapped[Bounty] = relationship("Bounty", back_populates="payment_authorizations")
    payment_transactions: Mapped[list[PaymentTransaction]] = relationship(
        "PaymentTransaction", back_populates="authorization"
    )


class PaymentTransaction(Base, TimestampMixin):
    """Payment transaction executed against a provider (Mock or PayPal Sandbox).

    SIMULATED transactions must never fabricate an external provider reference.
    Idempotency keys must be strictly unique to prevent double-spending or duplicate transfers.
    """

    __tablename__ = "payment_transactions"

    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        CheckConstraint(
            "execution_mode != 'SIMULATED' OR external_reference IS NULL",
            name="simulated_no_external_ref",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bounty_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("bounties.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    authorization_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("payment_authorizations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    execution_mode: Mapped[PaymentExecutionMode] = mapped_column(
        SQLEnum(PaymentExecutionMode, native_enum=False, length=20),
        nullable=False,
        default=PaymentExecutionMode.SIMULATED,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(PaymentStatus, native_enum=False, length=20),
        nullable=False,
        default=PaymentStatus.CREATED,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
    )
    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    task: Mapped[Task] = relationship("Task", back_populates="payment_transactions")
    bounty: Mapped[Bounty] = relationship("Bounty", back_populates="payment_transactions")
    authorization: Mapped[PaymentAuthorization | None] = relationship(
        "PaymentAuthorization", back_populates="payment_transactions"
    )


class AuditEvent(Base):
    """Immutable append-only audit event recording state changes, actor actions, and financial events."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
