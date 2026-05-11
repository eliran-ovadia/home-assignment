"""
Pytest fixtures for the test suite.

Integration tests in `tests/integration/` require a running PostgreSQL — they
share the same `Settings` (and therefore the same `DB_HOST` / `DB_PORT` /
`DB_PASSWORD`) as the running app. Locally, start it with `make dev-db`.
In CI, a `postgres:16-alpine` service container is provided by the workflow.

Per-test isolation strategy
---------------------------
Each integration test gets a fresh schema: `Base.metadata.drop_all` then
`create_all` at fixture setup, and `drop_all` at teardown. This is slower
than a session-scoped engine + per-test truncate (~150 ms × 17 tests
≈ 2.5 s overhead) but is bulletproof — every test starts from zero,
nothing leaks between tests, no fragile loop-scope plumbing.

The FastAPI app's `get_session` dependency is overridden inside the `app`
fixture so the routes use the same engine as the test code. The app's
lifespan (which would call `init_db()` on the *production* engine) is
not triggered, because `httpx.ASGITransport` doesn't run lifespan by
default — exactly what we want here.
"""

from __future__ import annotations

import datetime
import io
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.api.app import create_app
from src.core.database import build_database_url, get_session
from src.db.models import Base

# ── DB / app fixtures ────────────────────────────────────────────────────────


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Per-test engine. Drops + creates schema so every test starts from zero."""
    eng = create_async_engine(build_database_url(), pool_pre_ping=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await eng.dispose()


@pytest.fixture
def sessionmaker_(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """A sessionmaker bound to the per-test engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def db_session(
    sessionmaker_: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """A session for tests to read DB state directly when the API response isn't enough."""
    async with sessionmaker_() as session:
        yield session


@pytest.fixture
def app(sessionmaker_: async_sessionmaker[AsyncSession]) -> FastAPI:
    """FastAPI app with `get_session` overridden to use the per-test engine."""

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker_() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    fastapi_app = create_app()
    fastapi_app.dependency_overrides[get_session] = override_get_session
    return fastapi_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Async HTTP client speaking to the FastAPI app in-process (no real socket)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as cli:
        yield cli


# ── helpers ──────────────────────────────────────────────────────────────────

DEFAULT_USER_EMAIL = "alice@lumina.example"
OTHER_USER_EMAIL = "bob@lumina.example"

HEADER_ROW: list[str] = [
    "ClientId",
    "TransactionId",
    "ISIN",
    "Action",
    "Quantity",
    "Price",
    "Timestamp",
]

# Header → row-dict key mapping. Writing row data by looking up each column's
# key from this map (rather than relying on positional order matching
# HEADER_ROW) means reordering HEADER_ROW can't silently misalign the data.
_HEADER_TO_KEY: dict[str, str] = {
    "ClientId": "client_id",
    "TransactionId": "transaction_id",
    "ISIN": "isin",
    "Action": "action",
    "Quantity": "quantity",
    "Price": "price",
    "Timestamp": "timestamp",
}


def make_xlsx(
    rows: list[dict[str, Any]] | None = None,
    *,
    header: list[str] | None = None,
) -> bytes:
    """
    Build an in-memory `.xlsx` workbook with the standard SPEC §5.1 header and
    the supplied data rows. `header=None` uses the canonical header; pass a
    different list to exercise the "wrong columns" path.

    Row data is written in the same order as *header*, looked up via
    `_HEADER_TO_KEY` — so reordering `HEADER_ROW` (or passing a custom
    subset header) doesn't silently misalign data with column names.
    """
    workbook = Workbook()
    worksheet = workbook.active
    if header is None:
        header = HEADER_ROW
    worksheet.append(header)
    for r in rows or []:
        worksheet.append([r[_HEADER_TO_KEY[col]] for col in header])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def ts(day: int = 1, hour: int = 9, minute: int = 0) -> datetime.datetime:
    """Concise timestamp builder for test data."""
    return datetime.datetime(2026, 1, day, hour, minute, 0)


def row(
    *,
    client_id: str = "C001",
    transaction_id: str | None = None,
    isin: str = "ISIN_A",
    action: str = "Buy",
    quantity: float = 10.0,
    price: float = 100.0,
    timestamp: datetime.datetime | None = None,
) -> dict[str, Any]:
    """One transaction row in the shape `make_xlsx` consumes."""
    return {
        "client_id": client_id,
        "transaction_id": transaction_id
        or f"T{abs(hash((client_id, isin, action, quantity, price))) % 100000:05d}",
        "isin": isin,
        "action": action,
        "quantity": quantity,
        "price": price,
        "timestamp": timestamp or ts(),
    }


def upload_files(
    data: bytes, filename: str = "transactions.xlsx"
) -> dict[str, tuple[str, bytes, str]]:
    """Build the `files=` kwarg for `httpx.AsyncClient.post`."""
    return {
        "file": (
            filename,
            data,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }


def auth_header(email: str = DEFAULT_USER_EMAIL) -> dict[str, str]:
    """Shorthand for the `X-Session-Token: <email>` header."""
    return {"X-Session-Token": email}
