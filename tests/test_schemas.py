"""Tests for Pydantic domain schemas, data validation, and money alignment."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

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
from agentbounty.domain.money import from_minor_units, to_minor_units
from agentbounty.domain.schemas import (
    AgentCreate,
    AgentMessageCreate,
    AgentMessageRead,
    AgentRead,
    AuditEventCreate,
    AuditEventRead,
    BountyCreate,
    BountyRead,
    PaymentAuthorizationCreate,
    PaymentAuthorizationRead,
    PaymentTransactionCreate,
    PaymentTransactionRead,
    TaskCreate,
    TaskRead,
    TaskUpdate,
    VerificationCreate,
    VerificationRead,
    WorkerResultCreate,
    WorkerResultRead,
)
from agentbounty.exceptions import InvalidMoneyError


# --- Agent Schema Tests ---


def test_agent_create_valid() -> None:
    agent = AgentCreate(
        name="Worker Alpha",
        role=AgentRole.WORKER,
        description="Senior Python developer",
        capabilities=["python", "pytest"],
        status=AgentStatus.ACTIVE,
    )
    assert agent.name == "Worker Alpha"
    assert agent.role == AgentRole.WORKER
    assert agent.capabilities == ["python", "pytest"]


def test_agent_create_invalid_role() -> None:
    with pytest.raises(ValidationError):
        AgentCreate(
            name="Invalid",
            role="SUPERVISOR",  # type: ignore[arg-type]
            description="Invalid role",
        )


def test_agent_create_invalid_status() -> None:
    with pytest.raises(ValidationError):
        AgentCreate(
            name="Invalid",
            role=AgentRole.WORKER,
            description="Invalid status",
            status="SLEEPING",  # type: ignore[arg-type]
        )


# --- Task Schema Tests ---


def test_task_create_valid() -> None:
    now = datetime.now(timezone.utc)
    task = TaskCreate(
        title="Valid Task",
        description="A proper description",
        acceptance_criteria=["Criterion 1", "  Criterion 2  "],
        created_by="human-user",
        deadline=now,
    )
    assert task.title == "Valid Task"
    # Strips whitespace
    assert task.acceptance_criteria == ["Criterion 1", "Criterion 2"]
    assert task.deadline == now


def test_task_create_empty_title() -> None:
    with pytest.raises(ValidationError):
        TaskCreate(
            title="",
            description="Valid description",
            acceptance_criteria=["Valid"],
            created_by="human-user",
        )


def test_task_create_empty_acceptance_criteria_list() -> None:
    with pytest.raises(ValidationError):
        TaskCreate(
            title="Valid Title",
            description="Valid description",
            acceptance_criteria=[],
            created_by="human-user",
        )


def test_task_create_whitespace_only_criteria() -> None:
    with pytest.raises(ValidationError):
        TaskCreate(
            title="Valid Title",
            description="Valid description",
            acceptance_criteria=["   ", ""],
            created_by="human-user",
        )


def test_task_read_model() -> None:
    now = datetime.now(timezone.utc)
    task_read = TaskRead(
        id="task-123",
        title="Title",
        description="Desc",
        acceptance_criteria=["Criteria 1"],
        created_by="user",
        assigned_agent_id=None,
        status=TaskStatus.OPEN,
        deadline=None,
        created_at=now,
        updated_at=now,
    )
    assert task_read.status == TaskStatus.OPEN
    assert task_read.id == "task-123"


# --- Bounty Schema & Money Alignment Tests ---


def test_bounty_create_valid() -> None:
    bounty = BountyCreate(
        task_id="task-100",
        amount=Decimal("5.00"),
        currency="USD",
    )
    assert bounty.amount == Decimal("5.00")
    assert bounty.currency == "USD"
    assert bounty.minor_units == 500


def test_bounty_create_rejects_subcent_precision() -> None:
    """Schema validation must reject invalid precision immediately."""
    with pytest.raises((InvalidMoneyError, ValidationError)):
        BountyCreate(
            task_id="task-100",
            amount=Decimal("5.005"),
            currency="USD",
        )


def test_bounty_create_rejects_float() -> None:
    with pytest.raises(InvalidMoneyError):
        BountyCreate(
            task_id="task-100",
            amount=5.00,  # type: ignore[arg-type]
            currency="USD",
        )


def test_bounty_create_rejects_zero_or_negative() -> None:
    with pytest.raises(ValidationError):
        BountyCreate(
            task_id="task-100",
            amount=Decimal("0.00"),
            currency="USD",
        )

    with pytest.raises(ValidationError):
        BountyCreate(
            task_id="task-100",
            amount=Decimal("-5.00"),
            currency="USD",
        )


def test_bounty_read_converts_minor_units() -> None:
    now = datetime.now(timezone.utc)
    bounty_read = BountyRead(
        id="bounty-1",
        task_id="task-1",
        amount=1234,  # $12.34
        currency="USD",
        status=BountyStatus.OPEN,
        created_at=now,
        updated_at=now,
    )
    assert bounty_read.amount == 1234
    assert bounty_read.amount_decimal == Decimal("12.34")


# --- Payment Authorization Schema Tests ---


def test_payment_authorization_create_valid() -> None:
    auth = PaymentAuthorizationCreate(
        task_id="t1",
        bounty_id="b1",
        authorized_by="human-evaluator",
        decision=AuthorizationDecision.AUTHORIZED,
        authorized_amount=Decimal("5.00"),
        currency="USD",
        reason="Approved after verification",
    )
    assert auth.authorized_amount_minor_units == 500
    assert auth.decision == AuthorizationDecision.AUTHORIZED


def test_payment_authorization_create_invalid_decision() -> None:
    with pytest.raises(ValidationError):
        PaymentAuthorizationCreate(
            task_id="t1",
            bounty_id="b1",
            authorized_by="human-evaluator",
            decision="MAYBE",  # type: ignore[arg-type]
            authorized_amount=Decimal("5.00"),
        )


def test_payment_authorization_create_invalid_precision() -> None:
    with pytest.raises((InvalidMoneyError, ValidationError)):
        PaymentAuthorizationCreate(
            task_id="t1",
            bounty_id="b1",
            authorized_by="human-evaluator",
            decision=AuthorizationDecision.AUTHORIZED,
            authorized_amount=Decimal("5.001"),
        )


# --- Payment Transaction Schema Tests ---


def test_payment_transaction_create_simulated_valid() -> None:
    tx = PaymentTransactionCreate(
        task_id="t1",
        bounty_id="b1",
        provider_name="mock",
        execution_mode=PaymentExecutionMode.SIMULATED,
        amount=Decimal("5.00"),
        idempotency_key="unique-idempotency-key-01",
        external_reference=None,
    )
    assert tx.execution_mode == PaymentExecutionMode.SIMULATED
    assert tx.external_reference is None
    assert tx.minor_units == 500


def test_payment_transaction_create_simulated_rejects_external_ref() -> None:
    """Security rule: Simulated transactions must NEVER contain an external reference."""
    with pytest.raises(ValidationError, match="Simulated payment transactions cannot contain a fabricated"):
        PaymentTransactionCreate(
            task_id="t1",
            bounty_id="b1",
            provider_name="mock",
            execution_mode=PaymentExecutionMode.SIMULATED,
            amount=Decimal("5.00"),
            idempotency_key="unique-idempotency-key-01",
            external_reference="FAKE_PAYPAL_CAPTURE_123",
        )


def test_payment_transaction_create_sandbox_allows_external_ref() -> None:
    """Sandbox transactions may contain a real external reference."""
    tx = PaymentTransactionCreate(
        task_id="t1",
        bounty_id="b1",
        provider_name="paypal",
        execution_mode=PaymentExecutionMode.SANDBOX,
        amount=Decimal("5.00"),
        idempotency_key="unique-idempotency-key-02",
        external_reference="PAYPAL-BATCH-ID-999",
    )
    assert tx.execution_mode == PaymentExecutionMode.SANDBOX
    assert tx.external_reference == "PAYPAL-BATCH-ID-999"


def test_payment_transaction_create_short_idempotency_key() -> None:
    with pytest.raises(ValidationError):
        PaymentTransactionCreate(
            task_id="t1",
            bounty_id="b1",
            provider_name="mock",
            execution_mode=PaymentExecutionMode.SIMULATED,
            amount=Decimal("5.00"),
            idempotency_key="short",  # Min length is 8
        )


# --- Verification & AuditEvent Schema Tests ---


def test_verification_create_score_bounds() -> None:
    # Valid score
    v = VerificationCreate(
        worker_result_id="res-1",
        status=VerificationStatus.PASSED,
        score=95,
        explanation="Well done",
    )
    assert v.score == 95

    # Negative score rejected
    with pytest.raises(ValidationError):
        VerificationCreate(
            worker_result_id="res-1",
            status=VerificationStatus.PASSED,
            score=-5,
            explanation="Negative score",
        )

    # Score > 100 rejected
    with pytest.raises(ValidationError):
        VerificationCreate(
            worker_result_id="res-1",
            status=VerificationStatus.PASSED,
            score=105,
            explanation="Excessive score",
        )


def test_audit_event_create_and_read() -> None:
    now = datetime.now(timezone.utc)
    audit = AuditEventCreate(
        entity_type="Task",
        entity_id="task-001",
        event_type="TASK_ASSIGNED",
        actor_type="MANAGER",
        actor_id="manager-alpha",
        correlation_id="corr-999",
        payload={"worker_id": "worker-beta"},
    )
    assert audit.entity_type == "Task"
    assert audit.payload == {"worker_id": "worker-beta"}

    read_event = AuditEventRead(
        id="audit-uuid-123",
        entity_type=audit.entity_type,
        entity_id=audit.entity_id,
        event_type=audit.event_type,
        actor_type=audit.actor_type,
        actor_id=audit.actor_id,
        timestamp=now,
        correlation_id=audit.correlation_id,
        payload=audit.payload,
    )
    assert read_event.id == "audit-uuid-123"
    assert read_event.timestamp == now
