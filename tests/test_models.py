"""Tests for SQLAlchemy ORM models and database constraints."""

from datetime import datetime, timezone

import pytest
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


def test_create_all_orm_models(session: Session) -> None:
    """Verify that every required ORM model can be created and persisted."""
    # 1. Agent
    agent = Agent(
        name="Planner-Alpha",
        role=AgentRole.MANAGER,
        description="Coordinates and breaks down tasks",
        capabilities=["task-planning", "worker-selection"],
        status=AgentStatus.ACTIVE,
    )
    session.add(agent)
    session.flush()
    assert agent.id is not None
    assert isinstance(agent.created_at, datetime)
    assert agent.created_at.tzinfo is not None

    # 2. Worker Agent
    worker = Agent(
        name="Coder-Beta",
        role=AgentRole.WORKER,
        description="Executes code implementation tasks",
        capabilities=["python", "fastapi"],
        status=AgentStatus.ACTIVE,
    )
    session.add(worker)
    session.flush()

    # 3. Task
    task = Task(
        title="Implement Money Calculation Module",
        description="Ensure all float values are rejected and minor units used.",
        acceptance_criteria=["Zero float usage", "Full pytest coverage"],
        created_by="human-architect",
        assigned_agent_id=worker.id,
        status=TaskStatus.ASSIGNED,
    )
    session.add(task)
    session.flush()
    assert task.id is not None
    assert task.assigned_agent.id == worker.id

    # 4. Bounty
    bounty = Bounty(
        task_id=task.id,
        amount=500,  # $5.00
        currency="USD",
        status=BountyStatus.OPEN,
    )
    session.add(bounty)
    session.flush()
    assert bounty.id is not None
    assert task.bounty.id == bounty.id

    # 5. AgentMessage
    msg = AgentMessage(
        task_id=task.id,
        sender_type=SenderType.MANAGER,
        sender_id=agent.id,
        recipient_id=worker.id,
        message_type="TASK_ASSIGNED",
        content="Please implement the money utility adhering to specs.",
        message_metadata={"bounty_id": bounty.id},
    )
    session.add(msg)
    session.flush()
    assert msg.id is not None
    assert len(task.messages) == 1

    # 6. WorkerResult
    result = WorkerResult(
        task_id=task.id,
        worker_agent_id=worker.id,
        content="Module implemented in src/agentbounty/domain/money.py",
        artifact_metadata={"files": ["src/agentbounty/domain/money.py"]},
        submission_version=1,
    )
    session.add(result)
    session.flush()
    assert result.id is not None
    assert len(task.worker_results) == 1

    # 7. Verification
    verification = Verification(
        worker_result_id=result.id,
        status=VerificationStatus.PASSED,
        score=100,
        passed_criteria=["Zero float usage", "Full pytest coverage"],
        failed_criteria=[],
        explanation="All checks passed with 100% precision compliance.",
        verifier_type=VerifierType.AUTOMATED,
    )
    session.add(verification)
    session.flush()
    assert verification.id is not None
    assert len(result.verifications) == 1

    # 8. PaymentAuthorization
    auth = PaymentAuthorization(
        task_id=task.id,
        bounty_id=bounty.id,
        authorized_by="human-auditor-1",
        decision=AuthorizationDecision.AUTHORIZED,
        authorized_amount=500,
        currency="USD",
        reason="Verified deliverables satisfy criteria.",
    )
    session.add(auth)
    session.flush()
    assert auth.id is not None
    assert len(task.payment_authorizations) == 1

    # 9. PaymentTransaction
    tx = PaymentTransaction(
        task_id=task.id,
        bounty_id=bounty.id,
        authorization_id=auth.id,
        provider_name="mock",
        execution_mode=PaymentExecutionMode.SIMULATED,
        amount=500,
        currency="USD",
        status=PaymentStatus.SUCCEEDED,
        idempotency_key="tx-idem-key-1001",
        external_reference=None,  # simulated transactions must never fabricate an external ref
    )
    session.add(tx)
    session.flush()
    assert tx.id is not None
    assert len(task.payment_transactions) == 1
    assert tx.authorization.id == auth.id

    # 10. AuditEvent
    audit = AuditEvent(
        entity_type="Task",
        entity_id=task.id,
        event_type="TASK_COMPLETED",
        actor_type="SYSTEM",
        actor_id="market-engine",
        correlation_id="corr-xyz-123",
        payload={"bounty_id": bounty.id, "payout_amount": 500},
    )
    session.add(audit)
    session.flush()
    assert audit.id is not None
    assert audit.timestamp.tzinfo is not None


def test_unique_bounty_per_task_constraint(session: Session) -> None:
    """Enforce database constraint: a task cannot acquire multiple bounties."""
    task = Task(
        title="Single Bounty Task",
        description="Constraint test",
        acceptance_criteria=["Check 1"],
        created_by="user",
    )
    session.add(task)
    session.flush()

    b1 = Bounty(task_id=task.id, amount=100, currency="USD")
    session.add(b1)
    session.flush()

    b2 = Bounty(task_id=task.id, amount=200, currency="USD")
    session.add(b2)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_unique_idempotency_key_constraint(session: Session) -> None:
    """Unique constraint prevents duplicate idempotency keys on payment transactions."""
    task = Task(
        title="Idempotency Test Task",
        description="Testing duplicate keys",
        acceptance_criteria=["Criteria"],
        created_by="user",
    )
    session.add(task)
    session.flush()

    bounty = Bounty(task_id=task.id, amount=300, currency="USD")
    session.add(bounty)
    session.flush()

    tx1 = PaymentTransaction(
        task_id=task.id,
        bounty_id=bounty.id,
        provider_name="mock",
        execution_mode=PaymentExecutionMode.SIMULATED,
        amount=300,
        currency="USD",
        idempotency_key="reused-key-999",
    )
    session.add(tx1)
    session.flush()

    tx2 = PaymentTransaction(
        task_id=task.id,
        bounty_id=bounty.id,
        provider_name="mock",
        execution_mode=PaymentExecutionMode.SIMULATED,
        amount=300,
        currency="USD",
        idempotency_key="reused-key-999",
    )
    session.add(tx2)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_check_constraints_prevent_negative_money(session: Session) -> None:
    """Database check constraints reject negative money minor units."""
    task = Task(
        title="Check Constraint Task",
        description="Testing negative money in DB",
        acceptance_criteria=["Criteria"],
        created_by="user",
    )
    session.add(task)
    session.flush()

    bounty = Bounty(task_id=task.id, amount=-100, currency="USD")
    session.add(bounty)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_simulated_transaction_rejects_external_ref_db_constraint(session: Session) -> None:
    """Database check constraint rejects external_reference on SIMULATED payment transactions."""
    task = Task(
        title="Check Constraint Task",
        description="Testing simulated constraint in DB",
        acceptance_criteria=["Criteria"],
        created_by="user",
    )
    session.add(task)
    session.flush()

    bounty = Bounty(task_id=task.id, amount=500, currency="USD")
    session.add(bounty)
    session.flush()

    # Attempting to directly insert a simulated transaction with an external reference
    # must trigger the ck_transactions_simulated_no_external_ref check constraint
    tx = PaymentTransaction(
        task_id=task.id,
        bounty_id=bounty.id,
        provider_name="mock",
        execution_mode=PaymentExecutionMode.SIMULATED,
        amount=500,
        currency="USD",
        idempotency_key="sim-fail-key-01",
        external_reference="FABRICATED_REF",
    )
    session.add(tx)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
