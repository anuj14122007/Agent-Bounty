"""Alembic environment configuration for AgentBounty."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

from agentbounty.config.settings import get_settings
from agentbounty.persistence.base import Base
# Ensure all models are registered on Base.metadata
import agentbounty.persistence.models  # noqa: F401
from agentbounty.persistence.database import create_db_engine

# Interpret config file for Python logging.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Return database URL from settings or alembic config."""
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        url = get_settings().database_url
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = get_url()
    connectable = create_db_engine(url)

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
