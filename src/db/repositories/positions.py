"""Positions repository — per-(upload, client, ISIN) FIFO output."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy import insert as sa_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Position


async def bulk_insert(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    """Insert many position rows in one executemany."""
    if not rows:
        return
    await session.execute(sa_insert(Position), rows)


async def get_by_upload_and_client(
    session: AsyncSession, *, upload_id: int, client_id: str
) -> Sequence[Position]:
    """Return one client's positions for *upload_id*, ordered by ISIN."""
    stmt = (
        select(Position)
        .where(Position.upload_id == upload_id, Position.client_id == client_id)
        .order_by(Position.isin)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def count_by_upload(session: AsyncSession, upload_id: int) -> int:
    """Count positions for *upload_id* without fetching their rows."""
    stmt = select(func.count(Position.id)).where(Position.upload_id == upload_id)
    return int((await session.execute(stmt)).scalar_one())
