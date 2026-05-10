"""Client-analytics repository — precomputed per-client values."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import insert as sa_insert
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ClientAnalytic


async def bulk_insert(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    """Insert many client_analytics rows in one executemany."""
    if not rows:
        return
    await session.execute(sa_insert(ClientAnalytic), list(rows))


async def get_by_upload(session: AsyncSession, upload_id: int) -> Sequence[ClientAnalytic]:
    """Return all client_analytics rows for *upload_id*, ordered by client_id."""
    stmt = (
        select(ClientAnalytic)
        .where(ClientAnalytic.upload_id == upload_id)
        .order_by(ClientAnalytic.client_id)
    )
    result = await session.execute(stmt)
    return result.scalars().all()
