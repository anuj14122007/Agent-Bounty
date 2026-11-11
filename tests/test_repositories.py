"""Tests for repository CRUD operations, idempotency protection, and append-only audits."""

import pytest
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
from agentbounty.persistence.repositories import (
    AgentMessageRepository,
    AgentRepository,
    AuditEventRepository,
    BountyRepository,
    PaymentAuthorizationRepository,
    PaymentTransactionRepository,
    TaskRepository,
    VerificationRepository,
    WorkerResultRepository,
)


def test_agent_repository(session: Session) -> None:
    """Agent repository CRUD and filtering."""
    repo = AgentRepository(session)

    agent = repo.create(
        name="Worker-1",
        role=AgentRole.WORKER,
        description="General worker",
        capabilities=["data-analysis"],
        status=AgentStatus.ACTIVE,
    )
    assert agent.id is not None

    found = repo.get_by_id(agent.id)
    assert found is not None
    assert found.name == "Worker-1"

    updated = repo.update_status(agent.id, AgentStatus.BUSY)
    assert updated.status == AgentStatus.BUSY

    all_workers = repo.list_all(role=AgentRole.WORKER)
    assert len(all_workers) == 1
    assert all_workers[0].id == agent.id

    with pytest.raises(EntityNotFoundError):
        repo.get_by_id_or_raise("non-existent-id")


def test_task_repository(session: Session) -> None:
    """Task repository lifecycle and agent assignment."""
    agent_repo = AgentRepository(session)
    agent = agent_repo.create(
        name="Worker-2",
        role=AgentRole.WORKER,
        description="Worker for task",
    )

    task_repo = TaskRepository(session)
    task = task_repo.create(
        title="Sample Task",
        description="Description",
        acceptance_criteria=["Criterion 1"],
        created_by="user-admin",
    )
    assert task.status == TaskStatus.DRAFT

    assigned_task = task_repo.assign_agent(task.id, agent.id)
    assert assigned_task.assigned_agent_id == agent.id
    assert assigned_task.status == TaskStatus.ASSIGNED

    in_prog = task_repo.update_status(task.id, TaskStatus.IN_PROGRESS)
    assert in_prog.status == TaskStatus.IN_PROGRESS

    active_tasks = task_repo.list_tasks(status=TaskStatus.IN_PROGRESS)
    assert len(active_tasks) == 1


def test_bounty_repository_and_unique_constraint(session: Session) -> None:
    """Bounty repository enforces 1:1 bounty per task."""
    task_repo = TaskRepository(session)
    task = task_repo.create(
        title="Bounty Task",
        description="Testing bounties",
        acceptance_criteria=["Criterion 1"],
        created_by="user-admin",
    )

    bounty_repo = BountyRepository(session)
    bounty = bounty_repo.create(
        task_id=task.id,
        amount_minor_units=500,
        currency="USD",
    )
    assert bounty.amount == 500
    assert bounty.status == BountyStatus.OPEN

    # Duplicate bounty creation must raise DuplicateEntityError
    with pytest.raises(DuplicateEntityError, match="already has an active or associated bounty"):
        bounty_repo.create(task_id=task.id, amount_minor_units=1000)

    by_task = bounty_repo.get_by_task_id(task.id)
    assert by_task is not None
    assert by_task.id == bounty.id

    updated = bounty_repo.update_status(bounty.id, BountyStatus.RESERVED)
    assert updated.status == BountyStatus.RESERVED


def test_agent_message_repository(session: Session) -> None:
    """Message repository persists and orders messages by task."""
    task_repo = TaskRepository(session)
    task = task_repo.create(
        title="Chat Task",
        description="Task with conversation",
        acceptance_criteria=["Done"],
        created_by="user",
    )

    msg_repo = AgentMessageRepository(session)
    m1 = msg_repo.create(
        task_id=task.id,
        sender_type=SenderType.USER,
        sender_id="user-1",
        recipient_id="manager-1",
        message_type="TASK_SUBMITTED",
        content="Task submitted",
    )
    m2 = msg_repo.create(
        task_id=task.id,
        sender_type=SenderType.MANAGER,
        sender_id="manager-1",
        recipient_id="worker-1",
        message_type="DELEGATION",
        content="Delegating work",
    )

    messages = msg_repo.list_by_task(task.id)
    assert len(messages) == 2
    assert messages[0].id == m1.id
    assert messages[1].id == m2.id


def test_worker_result_and_verification_repositories(session: Session) -> None:
    """Worker results and verifications workflow."""
    agent_repo = AgentRepository(session)
    worker = agent_repo.create(name="Worker-3", role=AgentRole.WORKER, description="Worker")

    task_repo = TaskRepository(session)
    task = task_repo.create(
        title="Deliverable Task",
        description="Work with deliverable",
        acceptance_criteria=["Criterion 1"],
        created_by="user",
    )

    result_repo = WorkerResultRepository(session)
    result = result_repo.create(
        task_id=task.id,
        worker_agent_id=worker.id,
        content="Here is the finished work.",
        artifact_metadata={"hash": "abc123def"},
        submission_version=1,
    )
    assert result.submission_version == 1

    verif_repo = VerificationRepository(session)
    verif = verif_repo.create(
        worker_result_id=result.id,
        status=VerificationStatus.PASSED,
        explanation="Criterion 1 met successfully.",
        score=95,
        passed_criteria=["Criterion 1"],
        failed_criteria=[],
        verifier_type=VerifierType.AUTOMATED,
    )
    assert verif.status == VerificationStatus.PASSED

    reports = verif_repo.list_by_worker_result(result.id)
    assert len(reports) == 1
    assert reports[0].id == verif.id


def test_payment_authorization_repository(session: Session) -> None:
    """Payment authorizations store explicit human decision records."""
    task_repo = TaskRepository(session)
    task = task_repo.create(
        title="Payment Auth Task",
        description="Testing authorization",
        acceptance_criteria=["C1"],
        created_by="user",
    )
    bounty_repo = BountyRepository(session)
    bounty = bounty_repo.create(task_id=task.id, amount_minor_units=500)

    auth_repo = PaymentAuthorizationRepository(session)
    auth = auth_repo.create(
        task_id=task.id,
        bounty_id=bounty.id,
        authorized_by="human-reviewer",
        decision=AuthorizationDecision.AUTHORIZED,
        authorized_amount_minor_units=500,
        currency="USD",
        reason="Work verified and approved.",
    )
    assert auth.decision == AuthorizationDecision.AUTHORIZED

    authorizations = auth_repo.list_by_task(task.id)
    assert len(authorizations) == 1
    assert authorizations[0].authorized_by == "human-reviewer"


def test_payment_transaction_repository_idempotency(session: Session) -> None:
    """Payment transaction repository enforces unique idempotency keys."""
    task_repo = TaskRepository(session)
    task = task_repo.create(
        title="Transaction Task",
        description="Testing transactions",
        acceptance_criteria=["C1"],
        created_by="user",
    )
    bounty_repo = BountyRepository(session)
    bounty = bounty_repo.create(task_id=task.id, amount_minor_units=500)

    tx_repo = PaymentTransactionRepository(session)
    tx = tx_repo.create(
        task_id=task.id,
        bounty_id=bounty.id,
        provider_name="mock",
        execution_mode=PaymentExecutionMode.SIMULATED,
        amount_minor_units=500,
        idempotency_key="unique-idempotency-key-001",
    )
    assert tx.status == PaymentStatus.CREATED

    # Attempt duplicate idempotency key
    with pytest.raises(DuplicateEntityError, match="already exists"):
        tx_repo.create(
            task_id=task.id,
            bounty_id=bounty.id,
            provider_name="mock",
            execution_mode=PaymentExecutionMode.SIMULATED,
            amount_minor_units=500,
            idempotency_key="unique-idempotency-key-001",
        )

    # Status update
    updated_tx = tx_repo.update_status(tx.id, PaymentStatus.SUCCEEDED)
    assert updated_tx.status == PaymentStatus.SUCCEEDED
    assert updated_tx.completed_at is not None

    # Simulated transaction cannot have an external reference in create or update_status
    with pytest.raises(ValueError, match="Simulated payment transactions cannot contain a fabricated"):
        tx_repo.create(
            task_id=task.id,
            bounty_id=bounty.id,
            provider_name="mock",
            execution_mode=PaymentExecutionMode.SIMULATED,
            amount_minor_units=500,
            idempotency_key="unique-idempotency-key-002",
            external_reference="FABRICATED_REF_123",
        )

    with pytest.raises(ValueError, match="Simulated payment transactions cannot contain a fabricated"):
        tx_repo.update_status(tx.id, PaymentStatus.SUCCEEDED, external_reference="FABRICATED_REF_123")


def test_audit_event_repository_append_only(session: Session) -> None:
    """Audit events are append-only; update and delete operations must fail."""
    repo = AuditEventRepository(session)

    event = repo.append(
        entity_type="Task",
        entity_id="task-123",
        event_type="TASK_CREATED",
        actor_type="USER",
        actor_id="user-456",
        correlation_id="corr-789",
        payload={"action": "initial_creation"},
    )
    assert event.id is not None

    events = repo.list_by_entity("Task", "task-123")
    assert len(events) == 1
    assert events[0].payload == {"action": "initial_creation"}

    corr_events = repo.list_by_correlation_id("corr-789")
    assert len(corr_events) == 1

    # Invariant: update and delete operations are strictly prohibited
    with pytest.raises(AppendOnlyViolationError, match="cannot be updated"):
        repo.update(event.id)

    with pytest.raises(AppendOnlyViolationError, match="cannot be deleted"):
        repo.delete(event.id)
