"""
Analytics repository — live cross-table queries for the active upload.

These queries are intentionally kept in the DB layer (not in the domain layer)
because they're set-based aggregations Postgres can do far faster than Python.
The output shapes are plain tuples / dicts; the API layer (PR 4) wraps them
in Pydantic models.

Postgres-specific features used: `array_agg(DISTINCT ...)` in
`get_isin_concentration`. The spec targets PostgreSQL only (ADR 010 + SPEC §2),
so this is intentional, but worth knowing if the storage choice ever changes.

All `timestamp` columns are stored timezone-naive by convention (SPEC §3) and
treated as UTC by the ingestion validator (PR 3). Date-bucket queries below
inherit that convention.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, Row, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ClientAnalytic, Position, Transaction, Violation


async def get_top_traded_isins(
    session: AsyncSession, upload_id: int, limit: int = 3
) -> Sequence[tuple[str, int]]:
    """Top N ISINs by transaction count, descending. Empty if no transactions."""
    stmt = (
        select(Transaction.isin, func.count().label("c"))
        .where(Transaction.upload_id == upload_id)
        .group_by(Transaction.isin)
        .order_by(func.count().desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [(isin, int(c)) for isin, c in result.all()]


async def get_client_summary(session: AsyncSession, upload_id: int) -> list[dict[str, Any]]:
    """
    Return one row per client with transaction / position / violation counts.

    Three small GROUP BY queries are cheaper than a triple FULL OUTER JOIN at
    realistic scale, and the Python merge keeps the SQL readable.
    """
    counts: dict[str, dict[str, int]] = {}

    def _ensure_client_row(client_id: str) -> dict[str, int]:
        """Return the counts dict for *client_id*, creating it on first sight."""
        return counts.setdefault(
            client_id,
            {"transaction_count": 0, "position_count": 0, "violation_count": 0},
        )

    txn_q = (
        select(Transaction.client_id, func.count())
        .where(Transaction.upload_id == upload_id)
        .group_by(Transaction.client_id)
    )
    for cid, c in (await session.execute(txn_q)).all():
        _ensure_client_row(cid)["transaction_count"] = int(c)

    pos_q = (
        select(Position.client_id, func.count())
        .where(Position.upload_id == upload_id)
        .group_by(Position.client_id)
    )
    for cid, c in (await session.execute(pos_q)).all():
        _ensure_client_row(cid)["position_count"] = int(c)

    vio_q = (
        select(Violation.client_id, func.count())
        .where(Violation.upload_id == upload_id)
        .group_by(Violation.client_id)
    )
    for cid, c in (await session.execute(vio_q)).all():
        _ensure_client_row(cid)["violation_count"] = int(c)

    return [{"client_id": cid, **vals} for cid, vals in sorted(counts.items())]


async def get_isin_concentration(
    session: AsyncSession, upload_id: int, threshold: float = 0.70
) -> list[dict[str, Any]]:
    """
    ISINs held by more than `threshold` (default 70%) of the upload's clients.

    "Held" means `positions.quantity > 0` — closed-out positions don't count.
    Returns `[]` when no client has an open position.

    Uses Postgres `array_agg(DISTINCT client_id)` to fetch the client list in
    the same round trip as the count.
    """
    total_clients_q = select(func.count(distinct(Position.client_id))).where(
        Position.upload_id == upload_id, Position.quantity > 0
    )
    total_clients = int((await session.execute(total_clients_q)).scalar_one() or 0)
    if total_clients == 0:
        return []

    per_isin_q = (
        select(
            Position.isin,
            func.count(distinct(Position.client_id)).label("client_count"),
            func.array_agg(distinct(Position.client_id)).label("clients"),
        )
        .where(Position.upload_id == upload_id, Position.quantity > 0)
        .group_by(Position.isin)
    )
    out: list[dict[str, Any]] = []
    for isin, client_count, clients in (await session.execute(per_isin_q)).all():
        pct = client_count / total_clients
        if pct > threshold:
            out.append(
                {
                    "isin": isin,
                    "client_count": int(client_count),
                    "total_clients": total_clients,
                    "concentration_pct": pct,
                    "clients": sorted(clients),
                }
            )
    out.sort(key=lambda d: d["concentration_pct"], reverse=True)
    return out


async def get_most_traded_day(
    session: AsyncSession, upload_id: int
) -> tuple[datetime.date, int] | None:
    """
    The single calendar day with the most transactions, or None if empty.

    Date bucketing is performed against the stored timezone-naive timestamp
    (see module docstring) — i.e. the UTC date. If a future change adopts
    `TIMESTAMPTZ`, swap `cast(... AS DATE)` for `date_trunc('day', ... AT TIME
    ZONE 'UTC')` to keep the boundary explicit.
    """
    day = func.cast(Transaction.timestamp, Date).label("day")
    stmt = (
        select(day, func.count())
        .where(Transaction.upload_id == upload_id)
        .group_by(day)
        .order_by(func.count().desc())
        .limit(1)
    )
    row: Row[tuple[datetime.date, int]] | None = (await session.execute(stmt)).first()
    if row is None:
        return None
    return row[0], int(row[1])


async def get_top_realized_pnl_client(
    session: AsyncSession, upload_id: int
) -> tuple[str, Decimal] | None:
    """Client with the highest summed realized_pnl across all positions."""
    total = func.sum(Position.realized_pnl).label("total")
    stmt = (
        select(Position.client_id, total)
        .where(Position.upload_id == upload_id)
        .group_by(Position.client_id)
        .order_by(total.desc())
        .limit(1)
    )
    row: Row[tuple[str, Decimal]] | None = (await session.execute(stmt)).first()
    if row is None:
        return None
    return row[0], row[1]


async def get_win_rates(session: AsyncSession, upload_id: int) -> list[dict[str, Any]]:
    """
    Win-rate stats per client, sourced from `client_analytics`.

    The FIFO engine (PR 3) populates `winning_trades` and `total_trades`
    during upload processing. Clients with no completed trades are skipped
    so the API layer doesn't have to filter again. We also exclude rows
    where `winning_trades` is null while `total_trades` is set — that
    combination should never be written, but filtering here defends the
    `int(...)` cast below against a malformed upload.
    """
    stmt = (
        select(
            ClientAnalytic.client_id,
            ClientAnalytic.winning_trades,
            ClientAnalytic.total_trades,
        )
        .where(
            ClientAnalytic.upload_id == upload_id,
            ClientAnalytic.total_trades.is_not(None),
            ClientAnalytic.total_trades > 0,
            ClientAnalytic.winning_trades.is_not(None),
        )
        .order_by(ClientAnalytic.client_id)
    )
    out: list[dict[str, Any]] = []
    for cid, winning, total in (await session.execute(stmt)).all():
        out.append(
            {
                "client_id": cid,
                "winning_trades": int(winning),
                "total_trades": int(total),
            }
        )
    return out
