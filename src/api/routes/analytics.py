"""
`GET /api/v1/analytics` — composite view over the selected upload.

The four required sections (top_traded_isins, avg_holding_time_per_client,
most_volatile_client, isin_concentration) come from live SQL or from the
precomputed `client_analytics` table. The `bonus` block is populated when
the data is present and omitted otherwise (SPEC §4 "bonus omitted if no
data").
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter

from src.api.deps import CurrentUserDep, SessionDep
from src.api.schemas import (
    AnalyticsResponse,
    BonusAnalytics,
    HoldingTimeEntry,
    IsinConcentrationEntry,
    MostTradedDay,
    MostVolatileClient,
    TopRealizedPnlClient,
    TopTradedIsin,
    WinRateEntry,
)
from src.db.models import ClientAnalytic
from src.db.repositories import analytics as analytics_repo
from src.db.repositories import client_analytics as client_analytics_repo

router = APIRouter()


@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(user: CurrentUserDep, session: SessionDep) -> AnalyticsResponse:
    """Assemble the analytics response from the precomputed table + live SQL."""
    if user.last_viewed_upload_id is None:
        return _empty_response()

    upload_id = user.last_viewed_upload_id

    top_isins_rows = await analytics_repo.get_top_traded_isins(session, upload_id)
    concentration = await analytics_repo.get_isin_concentration(session, upload_id)
    client_analytic_rows = await client_analytics_repo.get_by_upload(session, upload_id)

    bonus = await _build_bonus(session, upload_id)

    return AnalyticsResponse(
        top_traded_isins=[TopTradedIsin(isin=i, transaction_count=c) for i, c in top_isins_rows],
        avg_holding_time_per_client=_holding_times(client_analytic_rows),
        most_volatile_client=_most_volatile(client_analytic_rows),
        isin_concentration=[IsinConcentrationEntry(**row) for row in concentration],
        bonus=bonus,
    )


def _empty_response() -> AnalyticsResponse:
    """SPEC §4: most_volatile_client is null when no data; bonus omitted."""
    return AnalyticsResponse(
        top_traded_isins=[],
        avg_holding_time_per_client=[],
        most_volatile_client=None,
        isin_concentration=[],
        bonus=None,
    )


def _holding_times(rows: list[ClientAnalytic] | Any) -> list[HoldingTimeEntry]:
    """One entry per client; `avg_holding_days` is None when the client has no completed trades."""
    return [
        HoldingTimeEntry(client_id=row.client_id, avg_holding_days=row.avg_holding_days)
        for row in rows
    ]


def _most_volatile(rows: list[ClientAnalytic] | Any) -> MostVolatileClient | None:
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


async def _build_bonus(session: Any, upload_id: int) -> BonusAnalytics | None:
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
                win_rate=_win_rate(row["winning_trades"], row["total_trades"]),
            )
            for row in win_rates_rows
        ],
        most_traded_day=most_traded_model,
    )


def _win_rate(winning: int, total: int) -> float:
    """Derived value — not stored. total > 0 is guaranteed by the repo filter."""
    return float(Decimal(winning) / Decimal(total))
