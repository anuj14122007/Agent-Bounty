"""Tests for database infrastructure, SQLite foreign key enforcement, and Alembic migrations."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from agentbounty.domain.enums import AgentRole, AgentStatus
from agentbounty.persistence.database import create_db_engine, init_db
from agentbounty.persistence.models import Agent, Bounty, Task


def test_sqlite_foreign_key_enforcement(session: Session) -> None:
    """Verify that SQLite connections enforce foreign-key constraints."""
    # Attempt to assign a task to a non-existent agent ID
    task = Task(
        title="Invalid Foreign Key Task",
        description="Should fail FK check",
        acceptance_criteria=["Criteria"],
        created_by="user",
        assigned_agent_id="00000000-0000-0000-0000-000000000000",
    )
    session.add(task)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    # Attempt to create a bounty for a non-existent task ID
    bounty = Bounty(
        task_id="00000000-0000-0000-0000-000000000000",
        amount=500,
        currency="USD",
    )
    session.add(bounty)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_data_survives_closing_and_reopening(tmp_path: Path) -> None:
    """Verify data persists on disk across closing and reopening SQLite connection."""
    db_file = tmp_path / "persistent_test.db"
    db_url = f"sqlite:///{db_file}"

    # 1. First connection: create tables and insert data
    engine1 = create_db_engine(db_url)
    init_db(engine1)
    sm1 = sessionmaker(bind=engine1)
    with sm1() as sess1:
        agent = Agent(
            name="Persistent-Agent",
            role=AgentRole.MANAGER,
            description="Tests persistence across restarts",
            capabilities=["testing"],
            status=AgentStatus.ACTIVE,
        )
        sess1.add(agent)
        sess1.commit()
        agent_id = agent.id

    engine1.dispose()

    # 2. Second connection: reopen same database file and verify data
    engine2 = create_db_engine(db_url)
    sm2 = sessionmaker(bind=engine2)
    with sm2() as sess2:
        retrieved = sess2.get(Agent, agent_id)
        assert retrieved is not None
        assert retrieved.name == "Persistent-Agent"
        assert retrieved.role == AgentRole.MANAGER

    engine2.dispose()


def test_alembic_fresh_database_migration(tmp_path: Path) -> None:
    """Verify that Alembic can create a fresh database directly from its initial migration."""
    migration_db_file = tmp_path / "migration_fresh.db"
    migration_db_url = f"sqlite:///{migration_db_file}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", migration_db_url)

    # Run upgrade to head
    command.upgrade(alembic_cfg, "head")

    # Inspect created tables in the fresh database
    engine = create_db_engine(migration_db_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    engine.dispose()

    expected_tables = {
        "alembic_version",
        "agents",
        "tasks",
        "bounties",
        "agent_messages",
        "worker_results",
        "verifications",
        "payment_authorizations",
        "payment_transactions",
        "audit_events",
    }
    assert expected_tables.issubset(tables)
