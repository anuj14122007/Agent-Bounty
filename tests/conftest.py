"""Pytest fixtures for AgentBounty test suite."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from agentbounty.config.settings import Settings
from agentbounty.persistence.base import Base
from agentbounty.persistence.database import create_db_engine, init_db


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Provide isolated test settings with a temporary SQLite database."""
    test_db_path = tmp_path / "test_agentbounty.db"
    return Settings(
        app_env="test",
        demo_mode=True,
        payment_provider="mock",
        paypal_payouts_enabled=False,
        paypal_environment="sandbox",
        max_bounty_usd="5.00",
        database_url=f"sqlite:///{test_db_path}",
    )


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Return a path for a temporary database file."""
    return tmp_path / "test_db.sqlite"


@pytest.fixture
def engine(temp_db_path: Path) -> Generator[Engine, None, None]:
    """Create a temporary file-based SQLite engine with Base metadata initialized."""
    db_url = f"sqlite:///{temp_db_path}"
    eng = create_db_engine(db_url)
    init_db(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Generator[Session, None, None]:
    """Provide an isolated database session with rollback/cleanup."""
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    sess = session_factory()
    try:
        yield sess
    finally:
        sess.rollback()
        sess.close()
