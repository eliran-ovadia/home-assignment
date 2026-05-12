"""Transactions repository — raw validated rows from one upload."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import insert as sa_insert
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
