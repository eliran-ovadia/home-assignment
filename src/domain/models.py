"""
Domain dataclasses — pure in-memory representations used by the FIFO engine,
the violation detectors, and the analytics layer. Zero DB or HTTP imports.

These are deliberately separate from the SQLAlchemy mapped classes in
`src.db.models`: domain code operates on these frozen dataclasses, then
the API layer converts them to row dicts for `bulk_insert`. The split keeps
the business logic testable without a database.

A note on "frozen": `frozen=True` prevents re-assigning fields after
construction, but for `list[...]` fields (notably on `FIFOResult`) it does
not prevent mutation of the list contents. Callers must not mutate those
lists after construction; in practice they are consumed immediately by the
API layer's bulk-insert step.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

# Violation type constants — referenced from the FIFO engine, detectors, and
# the API layer. Keep in sync with the violation matrix in SPEC §3.
VIOLATION_INVALID_VALUE = "INVALID_VALUE"
VIOLATION_SELL_BEFORE_BUY = "SELL_BEFORE_BUY"
VIOLATION_DAY_TRADING = "DAY_TRADING"
VIOLATION_RISK_CONCENTRATION = "RISK_CONCENTRATION"

SEVERITY_ERROR = "ERROR"
SEVERITY_FLAG = "FLAG"
SEVERITY_WARNING = "WARNING"

# Duplicated from `src.db.models` because the domain layer cannot import from
# `src.db` (layering rule: api → domain → db). Keep these two in sync.
ACTION_BUY = "Buy"
ACTION_SELL = "Sell"
VALID_ACTIONS = frozenset({ACTION_BUY, ACTION_SELL})


@dataclass(frozen=True, slots=True)
class RowError:
    """A validation failure for one row. Surfaced to the API as a 422 payload."""

    row_number: int
    transaction_id: str | None
    column: str
    reason: str


@dataclass(frozen=True, slots=True)
class RawRow:
    """
    A single parsed row from the Excel file, before validation.

    Field types are `Any` because openpyxl returns whatever the cell happens
    to contain — string, int, float, datetime, or None — and the validator
    is responsible for both type-checking and value-checking. `row_number`
    is the 1-based spreadsheet row (header is row 1, data starts at row 2).
    """

    row_number: int
    transaction_id: Any
    client_id: Any
    isin: Any
    action: Any
    quantity: Any
    price: Any
    timestamp: Any


@dataclass(frozen=True, slots=True)
class ValidatedRow:
    """
    A row that passed structural validation: every field has the canonical
    post-normalization shape (stripped strings, title-cased action, `Decimal`
    numerics, naïve UTC `datetime`).

    "Structural" only. Numeric values may still be ≤ 0 — those are flagged
    as INVALID_VALUE violations by `detect_invalid_values` in the domain
    layer, not rejected at parse time. Downstream consumers (FIFO,
    analytics) receive the *eligible* subset returned by that detector.
    """

    row_number: int
    transaction_id: str
    client_id: str
    isin: str
    action: str  # "Buy" or "Sell"
    quantity: Decimal
    price: Decimal
    timestamp: datetime.datetime


@dataclass(frozen=True, slots=True)
class CompletedTrade:
    """
    One matched buy→sell pair emitted by the FIFO engine. Multiple
    `CompletedTrade` rows can come out of a single Sell transaction when
    the sell crosses lot boundaries.
    """

    client_id: str
    isin: str
    quantity: Decimal
    buy_price: Decimal
    sell_price: Decimal
    buy_timestamp: datetime.datetime
    sell_timestamp: datetime.datetime

    @property
    def realized_pnl(self) -> Decimal:
        return self.quantity * (self.sell_price - self.buy_price)

    @property
    def is_winning(self) -> bool:
        return self.sell_price > self.buy_price


@dataclass(frozen=True, slots=True)
class Position:
    """
    A computed position for one (client, ISIN). Output of the FIFO engine,
    distinct from the SQLAlchemy `Position` ORM class in `src.db.models`.
    """

    client_id: str
    isin: str
    quantity: Decimal
    avg_cost: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    last_price: Decimal


@dataclass(frozen=True, slots=True)
class ViolationRecord:
    """
    A detected violation, ready to be persisted by the API layer.
    `transaction_id` and `isin` may be None for client-level violations
    (e.g. DAY_TRADING is a per-client signal, not tied to a specific row).
    """

    client_id: str
    violation_type: str
    severity: str
    description: str
    transaction_id: str | None = None
    isin: str | None = None


@dataclass(frozen=True, slots=True)
class FIFOResult:
    """Aggregate output of one FIFO pass over a whole upload."""

    positions: list[Position] = field(default_factory=list)
    completed_trades: list[CompletedTrade] = field(default_factory=list)
    sell_before_buy_violations: list[ViolationRecord] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ClientAnalyticsData:
    """
    Precomputed per-client analytics for one upload — mirrors the
    `client_analytics` DB row but as an in-memory dataclass.
    """

    client_id: str
    max_portfolio_value: Decimal
    min_portfolio_value: Decimal
    value_range: Decimal
    avg_holding_days: Decimal | None = None
    winning_trades: int | None = None
    total_trades: int | None = None


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    """
    Top-level output of the upload pipeline. Bundles everything the API
    layer needs to persist in one DB transaction.
    """

    valid_rows: list[ValidatedRow]
    positions: list[Position]
    violations: list[ViolationRecord]
    client_analytics: list[ClientAnalyticsData]
    completed_trades: list[CompletedTrade]
