"""Application bootstrap and dependency lifecycle management for AgentBounty UI."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import streamlit as st
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from agentbounty.agents.manager import ManagerAgent
from agentbounty.agents.registry import AgentRegistry
from agentbounty.config.settings import Settings, get_settings
from agentbounty.payments.authorization import PaymentAuthorizationService
from agentbounty.payments.execution import PaymentExecutionService
from agentbounty.payments.ledger import TransactionLedgerService
from agentbounty.payments.protocols import PaymentProvider
from agentbounty.payments.providers.mock import MockPaymentProvider
from agentbounty.payments.reconciliation import PaymentReconciliationService
from agentbounty.persistence.database import (
    create_db_engine,
    ensure_sqlite_parent_dir,
    get_session_factory,
    init_db,
)
from agentbounty.services.agent_communication import AgentCommunicationService
from agentbounty.services.task_orchestration import TaskOrchestrationService
from agentbounty.services.verification import VerificationEngine

logger = logging.getLogger(__name__)


@dataclass
class AppServices:
    """Consolidated container for initialized backend services."""

    settings: Settings
    registry: AgentRegistry
    manager: ManagerAgent
    verification_engine: VerificationEngine
    orchestrator: TaskOrchestrationService
    communication: AgentCommunicationService
    auth_service: PaymentAuthorizationService
    exec_service: PaymentExecutionService
    recon_service: PaymentReconciliationService
    ledger_service: TransactionLedgerService
    payment_provider: PaymentProvider


def run_database_migrations(engine: Engine, database_url: str) -> None:
    """Apply Alembic migrations to head, falling back to init_db if alembic config is unavailable."""
    ensure_sqlite_parent_dir(database_url)
    repo_root = Path(__file__).resolve().parent.parent
    alembic_ini = repo_root / "alembic.ini"

    if alembic_ini.exists():
        try:
            cfg = Config(str(alembic_ini))
            cfg.set_main_option("sqlalchemy.url", database_url)
            command.upgrade(cfg, "head")
            logger.info("Alembic schema migrations applied successfully.")
            return
        except Exception as err:
            logger.warning(
                "Alembic upgrade encountered error (%s); falling back to direct schema creation.",
                err,
            )

    # Fallback to direct SQLAlchemy create_all if alembic failed or alembic.ini missing
    init_db(engine)


@st.cache_resource(show_spinner=False)
def get_cached_engine_and_factory() -> tuple[Engine, sessionmaker[Session], Settings]:
    """Create and cache long-lived SQLAlchemy Engine and sessionmaker."""
    settings = get_settings()
    engine = create_db_engine(database_url=settings.database_url, echo=False)
    run_database_migrations(engine, settings.database_url)
    factory = get_session_factory(engine)
    return engine, factory, settings


def sync_registry_agents(session: Session) -> AgentRegistry:
    """Instantiate agent registry and synchronize deterministic agent profiles to the database."""
    registry = AgentRegistry()
    manager = ManagerAgent(registry=registry)
    # Synchronize specialist workers and manager without creating duplicates
    registry.sync_with_db(session, include_agents=[manager])
    session.commit()
    return registry


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Yield a transactional database session from the cached session factory."""
    _, factory, _ = get_cached_engine_and_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_payment_provider(settings: Settings) -> PaymentProvider:
    """Instantiate payment provider based on active settings. Default to MockPaymentProvider."""
    # Strict DEMO invariant: Mock provider is used for offline demo
    return MockPaymentProvider()


def get_app_services(session: Session) -> AppServices:
    """Build initialized backend services bound to the provided session."""
    settings = get_settings()
    registry = AgentRegistry()
    manager = ManagerAgent(registry=registry, settings=settings)
    verification_engine = VerificationEngine()
    comm_service = AgentCommunicationService(session)
    orchestrator = TaskOrchestrationService(
        session=session,
        registry=registry,
        manager=manager,
        verification_engine=verification_engine,
        communication_service=comm_service,
        settings=settings,
    )
    auth_service = PaymentAuthorizationService(session=session, settings=settings)
    provider = get_payment_provider(settings)
    exec_service = PaymentExecutionService(session=session, settings=settings, provider=provider)
    recon_service = PaymentReconciliationService(session=session, provider=provider)
    ledger_service = TransactionLedgerService(session=session)

    return AppServices(
        settings=settings,
        registry=registry,
        manager=manager,
        verification_engine=verification_engine,
        orchestrator=orchestrator,
        communication=comm_service,
        auth_service=auth_service,
        exec_service=exec_service,
        recon_service=recon_service,
        ledger_service=ledger_service,
        payment_provider=provider,
    )


def bootstrap_application() -> tuple[bool, str]:
    """Ensure database is migrated, agents are synchronized, and backend is operational."""
    try:
        _, factory, settings = get_cached_engine_and_factory()
        session = factory()
        try:
            sync_registry_agents(session)
        finally:
            session.close()
        return True, "Application initialized successfully."
    except Exception as err:
        logger.exception("Application bootstrap failed.")
        return False, f"Database initialization failed: {err}"
