"""Database engine, session management, and SQLite foreign-key enforcement."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, pool
from sqlalchemy.orm import Session, sessionmaker

from agentbounty.config.settings import get_settings
from agentbounty.persistence.base import Base


def _enable_sqlite_foreign_keys(dbapi_connection: object, connection_record: object) -> None:
    """Enforce foreign key constraints on SQLite connections."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


def ensure_sqlite_parent_dir(database_url: str) -> None:
    """Ensure parent directory exists for SQLite file databases."""
    if database_url.startswith("sqlite:///") and not database_url.startswith("sqlite:///:memory:"):
        db_path_str = database_url.replace("sqlite:///", "")
        db_path = Path(db_path_str).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(database_url: str | None = None, echo: bool = False) -> Engine:
    """Create a configured SQLAlchemy engine with SQLite foreign key enforcement.

    Args:
        database_url: Optional database connection URL. If omitted, uses get_settings().database_url.
        echo: Whether to log SQL statements.

    Returns:
        Configured SQLAlchemy Engine.
    """
    url = database_url or get_settings().database_url
    ensure_sqlite_parent_dir(url)

    # SQLite file-based connections use NullPool to cleanly release connections and prevent resource leaks
    engine_kwargs: dict[str, object] = {"echo": echo, "future": True}
    if url.startswith("sqlite") and not url.startswith("sqlite:///:memory:"):
        engine_kwargs["poolclass"] = pool.NullPool

    engine = create_engine(url, **engine_kwargs)

    # Attach SQLite foreign key PRAGMA listener
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)

    return engine


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    """Create a configured sessionmaker."""
    eng = engine or create_db_engine()
    return sessionmaker(bind=eng, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def session_scope(
    session_factory: sessionmaker[Session] | None = None,
) -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    factory = session_factory or get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(engine: Engine) -> None:
    """Initialize database tables via metadata create_all (for testing / programmatic setup)."""
    Base.metadata.create_all(bind=engine)
