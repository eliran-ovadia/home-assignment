"""Positions repository — per-(upload, client, ISIN) FIFO output."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import insert as sa_insert
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Position


async def bulk_insert(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    """Insert many position rows in one executemany."""
    if not rows:
        return
    await session.execute(sa_insert(Position), list(rows))


async def get_all_by_upload(session: AsyncSession, upload_id: int) -> Sequence[Position]:
    """Return every position for *upload_id*, ordered by (client_id, isin)."""
    stmt = (
        select(Position)
        .where(Position.upload_id == upload_id)
        .order_by(Position.client_id, Position.isin)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


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
