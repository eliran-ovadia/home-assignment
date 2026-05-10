"""Violations repository — detected rule violations per upload."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy import insert as sa_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Violation


async def bulk_insert(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    """Insert many violation rows in one executemany."""
    if not rows:
        return
    await session.execute(sa_insert(Violation), list(rows))


async def get_by_upload(
    session: AsyncSession,
    *,
    upload_id: int,
    client_id: str | None = None,
    violation_type: str | None = None,
) -> Sequence[Violation]:
    """
    Return violations for *upload_id*, optionally filtered by client and/or type.

    Ordering: detected_at then id, so retrieval is deterministic.
    """
    stmt: Select[tuple[Violation]] = select(Violation).where(Violation.upload_id == upload_id)
    if client_id is not None:
        stmt = stmt.where(Violation.client_id == client_id)
    if violation_type is not None:
        stmt = stmt.where(Violation.violation_type == violation_type)
    stmt = stmt.order_by(Violation.detected_at, Violation.id)
    result = await session.execute(stmt)
    return result.scalars().all()
