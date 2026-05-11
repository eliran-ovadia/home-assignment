"""Transactions repository — raw validated rows from one upload."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import insert as sa_insert
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Transaction


async def bulk_insert(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    """
    Insert many transaction rows in one executemany.

    Each dict must contain: upload_id, transaction_id, client_id, isin, action,
    quantity, price, timestamp.  `created_at` is filled by the DB default.
    """
    if not rows:
        return
    await session.execute(sa_insert(Transaction), rows)


async def get_by_upload(session: AsyncSession, upload_id: int) -> Sequence[Transaction]:
    """Return all transactions for *upload_id*, ordered by timestamp."""
    stmt = (
        select(Transaction)
        .where(Transaction.upload_id == upload_id)
        .order_by(Transaction.timestamp, Transaction.id)
    )
    result = await session.execute(stmt)
    return result.scalars().all()
