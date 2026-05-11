"""
`GET /api/v1/analytics` — composite view over the selected upload.

The four required sections (top_traded_isins, avg_holding_time_per_client,
most_volatile_client, isin_concentration) come from live SQL or from the
precomputed `client_analytics` table. The `bonus` block is populated when
the data is present and omitted otherwise (SPEC §4 "bonus omitted if no
data").

Non-endpoint helpers (response shape, bonus assembly) live in
`src/api/route_helpers/analytics.py`.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.api.deps import CurrentUserDep, SessionDep
from src.api.route_helpers.analytics import (
    build_bonus,
    empty_response,
    holding_times,
    most_volatile,
)
from src.api.schemas import (
    AnalyticsResponse,
    IsinConcentrationEntry,
    TopTradedIsin,
)
from src.db.repositories import analytics as analytics_repo
from src.db.repositories import client_analytics as client_analytics_repo

router = APIRouter()


@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(user: CurrentUserDep, session: SessionDep) -> AnalyticsResponse:
    """Assemble the analytics response from the precomputed table + live SQL."""
    if user.last_viewed_upload_id is None:
        return empty_response()

    upload_id = user.last_viewed_upload_id

    top_isins_rows = await analytics_repo.get_top_traded_isins(session, upload_id)
    concentration = await analytics_repo.get_isin_concentration(session, upload_id)
    client_analytic_rows = await client_analytics_repo.get_by_upload(session, upload_id)

    bonus = await build_bonus(session, upload_id)

    return AnalyticsResponse(
        top_traded_isins=[TopTradedIsin(isin=i, transaction_count=c) for i, c in top_isins_rows],
        avg_holding_time_per_client=holding_times(client_analytic_rows),
        most_volatile_client=most_volatile(client_analytic_rows),
        isin_concentration=[IsinConcentrationEntry(**row) for row in concentration],
        bonus=bonus,
    )
