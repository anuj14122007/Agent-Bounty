"""001_initial_schema: Initial schema for AgentBounty entities

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-11-11 19:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. agents
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agents")),
    )
    op.create_index(op.f("ix_agents_status"), "agents", ["status"], unique=False)

    # 2. tasks
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("assigned_agent_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_agent_id"],
            ["agents.id"],
            name=op.f("fk_tasks_assigned_agent_id_agents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index(op.f("ix_tasks_status"), "tasks", ["status"], unique=False)
    op.create_index(op.f("ix_tasks_assigned_agent_id"), "tasks", ["assigned_agent_id"], unique=False)

    # 3. bounties
    op.create_table(
        "bounties",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount >= 0", name="amount_non_negative"),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_bounties_task_id_tasks"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bounties")),
        sa.UniqueConstraint("task_id", name=op.f("uq_bounties_task_id")),
    )
    op.create_index(op.f("ix_bounties_status"), "bounties", ["status"], unique=False)
    op.create_index(op.f("ix_bounties_task_id"), "bounties", ["task_id"], unique=False)

    # 4. agent_messages
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("sender_type", sa.String(length=20), nullable=False),
        sa.Column("sender_id", sa.String(length=100), nullable=True),
        sa.Column("recipient_id", sa.String(length=100), nullable=True),
        sa.Column("message_type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("message_metadata", sa.JSON(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_agent_messages_task_id_tasks"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_messages")),
    )
    op.create_index(op.f("ix_agent_messages_task_id"), "agent_messages", ["task_id"], unique=False)
    op.create_index(op.f("ix_agent_messages_timestamp"), "agent_messages", ["timestamp"], unique=False)

    # 5. worker_results
    op.create_table(
        "worker_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("worker_agent_id", sa.String(length=36), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("artifact_metadata", sa.JSON(), nullable=False),
        sa.Column("submission_version", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_worker_results_task_id_tasks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["worker_agent_id"],
            ["agents.id"],
            name=op.f("fk_worker_results_worker_agent_id_agents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_results")),
    )
    op.create_index(op.f("ix_worker_results_task_id"), "worker_results", ["task_id"], unique=False)
    op.create_index(op.f("ix_worker_results_worker_agent_id"), "worker_results", ["worker_agent_id"], unique=False)

    # 6. verifications
    op.create_table(
        "verifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("worker_result_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("passed_criteria", sa.JSON(), nullable=False),
        sa.Column("failed_criteria", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("verifier_type", sa.String(length=30), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["worker_result_id"],
            ["worker_results.id"],
            name=op.f("fk_verifications_worker_result_id_worker_results"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verifications")),
    )
    op.create_index(op.f("ix_verifications_status"), "verifications", ["status"], unique=False)
    op.create_index(op.f("ix_verifications_worker_result_id"), "verifications", ["worker_result_id"], unique=False)

    # 7. payment_authorizations
    op.create_table(
        "payment_authorizations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("bounty_id", sa.String(length=36), nullable=False),
        sa.Column("authorized_by", sa.String(length=100), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("authorized_amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.CheckConstraint("authorized_amount >= 0", name="amount_non_negative"),
        sa.ForeignKeyConstraint(
            ["bounty_id"],
            ["bounties.id"],
            name=op.f("fk_payment_authorizations_bounty_id_bounties"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_payment_authorizations_task_id_tasks"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_authorizations")),
    )
    op.create_index(op.f("ix_payment_authorizations_bounty_id"), "payment_authorizations", ["bounty_id"], unique=False)
    op.create_index(op.f("ix_payment_authorizations_decision"), "payment_authorizations", ["decision"], unique=False)
    op.create_index(op.f("ix_payment_authorizations_task_id"), "payment_authorizations", ["task_id"], unique=False)

    # 8. payment_transactions
    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("bounty_id", sa.String(length=36), nullable=False),
        sa.Column("authorization_id", sa.String(length=36), nullable=True),
        sa.Column("provider_name", sa.String(length=50), nullable=False),
        sa.Column("execution_mode", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("external_reference", sa.String(length=255), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount >= 0", name="amount_non_negative"),
        sa.CheckConstraint(
            "execution_mode != 'SIMULATED' OR external_reference IS NULL",
            name="simulated_no_external_ref",
        ),
        sa.ForeignKeyConstraint(
            ["authorization_id"],
            ["payment_authorizations.id"],
            name=op.f("fk_payment_transactions_authorization_id_payment_authorizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["bounty_id"],
            ["bounties.id"],
            name=op.f("fk_payment_transactions_bounty_id_bounties"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_payment_transactions_task_id_tasks"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_transactions")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_payment_transactions_idempotency_key")),
    )
    op.create_index(op.f("ix_payment_transactions_authorization_id"), "payment_transactions", ["authorization_id"], unique=False)
    op.create_index(op.f("ix_payment_transactions_bounty_id"), "payment_transactions", ["bounty_id"], unique=False)
    op.create_index(op.f("ix_payment_transactions_idempotency_key"), "payment_transactions", ["idempotency_key"], unique=False)
    op.create_index(op.f("ix_payment_transactions_status"), "payment_transactions", ["status"], unique=False)
    op.create_index(op.f("ix_payment_transactions_task_id"), "payment_transactions", ["task_id"], unique=False)

    # 9. audit_events
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor_type", sa.String(length=50), nullable=False),
        sa.Column("actor_id", sa.String(length=100), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_correlation_id"), "audit_events", ["correlation_id"], unique=False)
    op.create_index(op.f("ix_audit_events_entity_id"), "audit_events", ["entity_id"], unique=False)
    op.create_index(op.f("ix_audit_events_entity_type"), "audit_events", ["entity_type"], unique=False)
    op.create_index(op.f("ix_audit_events_event_type"), "audit_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_audit_events_timestamp"), "audit_events", ["timestamp"], unique=False)


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("payment_transactions")
    op.drop_table("payment_authorizations")
    op.drop_table("verifications")
    op.drop_table("worker_results")
    op.drop_table("agent_messages")
    op.drop_table("bounties")
    op.drop_table("tasks")
    op.drop_table("agents")
