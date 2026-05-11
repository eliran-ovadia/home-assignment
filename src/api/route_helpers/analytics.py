"""
Helpers for `src/api/routes/analytics.py` — response-shape assembly and
the bonus-section orchestration. Split out so the route file contains
only the endpoint.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    AnalyticsResponse,
    BonusAnalytics,
    HoldingTimeEntry,
    MostTradedDay,
    MostVolatileClient,
    TopRealizedPnlClient,
    WinRateEntry,
)
from src.db.models import ClientAnalytic
from src.db.repositories import analytics as analytics_repo


def empty_response() -> AnalyticsResponse:
    """SPEC §4: most_volatile_client is null when no data; bonus omitted."""
    return AnalyticsResponse(
        top_traded_isins=[],
        avg_holding_time_per_client=[],
        most_volatile_client=None,
        isin_concentration=[],
        bonus=None,
    )


def holding_times(rows: Sequence[ClientAnalytic]) -> list[HoldingTimeEntry]:
    """One entry per client; `avg_holding_days` is None when the client has no completed trades."""
    return [
        HoldingTimeEntry(client_id=row.client_id, avg_holding_days=row.avg_holding_days)
        for row in rows
    ]


def most_volatile(rows: Sequence[ClientAnalytic]) -> MostVolatileClient | None:
    """Client with the largest value_range, or None if there are no rows."""
    if not rows:
        return None
    top = max(rows, key=lambda r: r.value_range)
    return MostVolatileClient(
        client_id=top.client_id,
        max_portfolio_value=top.max_portfolio_value,
        min_portfolio_value=top.min_portfolio_value,
        value_range=top.value_range,
    )


async def build_bonus(session: AsyncSession, upload_id: int) -> BonusAnalytics | None:
    """
    Bonus section: top realized P&L client, win rates, most traded day.
    Returns None when none of the three have data — keeps the response
    shape stable per SPEC §4 ("bonus: omitted if no data").
    """
    top_pnl = await analytics_repo.get_top_realized_pnl_client(session, upload_id)
    win_rates_rows = await analytics_repo.get_win_rates(session, upload_id)
    most_traded = await analytics_repo.get_most_traded_day(session, upload_id)

    if top_pnl is None and not win_rates_rows and most_traded is None:
        return None

    top_pnl_model = (
        TopRealizedPnlClient(client_id=top_pnl[0], realized_pnl=top_pnl[1])
        if top_pnl is not None
        else None
    )
    most_traded_model = (
        MostTradedDay(date=most_traded[0], transaction_count=most_traded[1])
        if most_traded is not None
        else None
    )
    return BonusAnalytics(
        top_realized_pnl_client=top_pnl_model,
        win_rate_per_client=[
            WinRateEntry(
                client_id=row["client_id"],
                winning_trades=row["winning_trades"],
                total_trades=row["total_trades"],
                win_rate=win_rate(row["winning_trades"], row["total_trades"]),
            )
            for row in win_rates_rows
        ],
        most_traded_day=most_traded_model,
    )


def win_rate(winning: int, total: int) -> float:
    """
    Derived value — not stored.

    Defensive: returns 0.0 when *total* is non-positive, even though the
    repository filter (`get_win_rates` in `db.repositories.analytics`) is
    documented to exclude `total_trades <= 0` rows. Trusting that contract
    silently across module boundaries is a fragile pattern; an explicit
    guard here costs one branch and removes a cross-file invariant the
    next maintainer would have to discover.
    """
    if total <= 0:
        return 0.0
    return float(Decimal(winning) / Decimal(total))
