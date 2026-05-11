"""
Alembic environment.

Composes the database URL from the same `Settings` + `SecretStr` pipeline as
the application (no credentials hardcoded in `alembic.ini`). Online runs use
`create_async_engine` and bridge to Alembic's sync API via
`connection.run_sync(...)`.
"""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.database import build_database_url
from src.db.models import Base

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (used by `alembic upgrade head --sql`)."""
    context.configure(
        url=build_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live database via the async engine."""
    engine = create_async_engine(build_database_url(), pool_pre_ping=True)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
