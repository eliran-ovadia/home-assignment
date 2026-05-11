"""
Async SQLAlchemy engine and session lifecycle.

The engine is created lazily at app startup (`init_db`) and disposed at
shutdown (`close_db`). Routes acquire sessions via `get_session()`, which is
designed to be used as a FastAPI dependency:

    from fastapi import Depends
    from src.core.database import get_session

    @router.get("/clients")
    async def list_clients(session: AsyncSession = Depends(get_session)):
        ...

All connection details — including the password — come from
`src.core.config.settings`, which is populated from `.env` (local) or the OS
environment (CI / production).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import quote_plus

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def build_database_url() -> str:
    """Compose the asyncpg URL from settings."""
    user = quote_plus(settings.db_user)
    password = quote_plus(settings.db_password.get_secret_value())
    return (
        f"postgresql+asyncpg://{user}:{password}"
        f"@{settings.db_host}:{settings.db_port}/{settings.db_name}"
    )


def init_db() -> None:
    """Create the engine and sessionmaker. Idempotent."""
    global _engine, _sessionmaker
    if _engine is not None:
        return
    _engine = create_async_engine(
        build_database_url(),
        # `pool_pre_ping` issues a cheap SELECT 1 before handing out a connection,
        # which prevents stale-connection errors when Postgres or a load balancer
        # closes idle sockets between requests.
        pool_pre_ping=True,
    )
    _sessionmaker = async_sessionmaker(
        _engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )


async def close_db() -> None:
    """Dispose the engine and clear module state. Idempotent."""
    global _engine, _sessionmaker
    if _engine is None:
        return
    await _engine.dispose()
    _engine = None
    _sessionmaker = None


def get_engine() -> AsyncEngine:
    """Return the active engine. Raises if `init_db()` hasn't been called."""
    engine = _engine
    if engine is None:
        raise RuntimeError("Database engine not initialised. Call init_db() first.")
    return engine


async def get_session() -> AsyncIterator[AsyncSession]:
    """
    Yield an `AsyncSession` for one request and clean it up on exit.

    Designed for `Depends(get_session)`. Errors trigger a rollback; the session
    is always closed via the async context manager.
    """
    sessionmaker = _sessionmaker
    if sessionmaker is None:
        raise RuntimeError("Database engine not initialised. Call init_db() first.")
    async with sessionmaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
