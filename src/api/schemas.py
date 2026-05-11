"""
Pydantic response/request models for every endpoint in SPEC §4.

These are the *wire* shapes — they don't depend on SQLAlchemy or on the
domain dataclasses. Routes convert from DB rows / domain objects into
these models at the boundary, which is the only place that knows about
JSON keys, ISO-8601 timestamps, and the API versioning surface.

`from_attributes=True` is set everywhere we read from an ORM row directly,
so a `Position` (ORM) can be validated into `PositionResponse` (wire) via
`PositionResponse.model_validate(orm_row)` without a manual field copy.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# ── upload-transactions ──────────────────────────────────────────────────────


class UploadSummary(BaseModel):
    transactions_loaded: int
    positions_computed: int
    violations_detected: int


class UploadResponse(BaseModel):
    upload_id: int
    status: str = "success"
    summary: UploadSummary


class RejectedRow(BaseModel):
    """One invalid row in a 422 response. `transaction_id` may be missing or unparseable."""

    row_number: int
    transaction_id: str | None = None
    column: str
    reason: str


class RejectedRowsResponse(BaseModel):
    """422 body when one or more rows fail validation."""

    detail: str = "Upload rejected: file contains invalid rows"
    rejected_rows: list[RejectedRow]


# ── clients ──────────────────────────────────────────────────────────────────


class ClientSummary(BaseModel):
    client_id: str
    transaction_count: int
    position_count: int
    violation_count: int


class PositionResponse(BaseModel):
    """A single position row. Matches `positions` table columns minus FK and id."""

    model_config = ConfigDict(from_attributes=True)

    isin: str
    quantity: Decimal
    avg_cost: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    last_price: Decimal


# ── violations ───────────────────────────────────────────────────────────────


class ViolationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_id: str | None
    client_id: str
    isin: str | None
    violation_type: str
    severity: str
    description: str
    detected_at: datetime.datetime


# ── analytics ────────────────────────────────────────────────────────────────


class TopTradedIsin(BaseModel):
    isin: str
    transaction_count: int


class HoldingTimeEntry(BaseModel):
    client_id: str
    avg_holding_days: Decimal | None


class MostVolatileClient(BaseModel):
    client_id: str
    max_portfolio_value: Decimal
    min_portfolio_value: Decimal
    value_range: Decimal


class IsinConcentrationEntry(BaseModel):
    isin: str
    client_count: int
    total_clients: int
    concentration_pct: float
    clients: list[str]


class TopRealizedPnlClient(BaseModel):
    client_id: str
    realized_pnl: Decimal


class WinRateEntry(BaseModel):
    client_id: str
    win_rate: float
    winning_trades: int
    total_trades: int


class MostTradedDay(BaseModel):
    date: datetime.date
    transaction_count: int


class BonusAnalytics(BaseModel):
    top_realized_pnl_client: TopRealizedPnlClient | None = None
    win_rate_per_client: list[WinRateEntry] = Field(default_factory=list)
    most_traded_day: MostTradedDay | None = None


class AnalyticsResponse(BaseModel):
    top_traded_isins: list[TopTradedIsin]
    avg_holding_time_per_client: list[HoldingTimeEntry]
    most_volatile_client: MostVolatileClient | None
    isin_concentration: list[IsinConcentrationEntry]
    bonus: BonusAnalytics | None = None


# ── uploads ──────────────────────────────────────────────────────────────────


class UploadHistoryItem(BaseModel):
    """One upload in the shared pool. `is_last_viewed` is per-current-user."""

    id: int
    filename: str
    row_count: int
    violation_count: int
    uploaded_at: datetime.datetime
    is_last_viewed: bool


class SetLastViewedRequest(BaseModel):
    upload_id: int
