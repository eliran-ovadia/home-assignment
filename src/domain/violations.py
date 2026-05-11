"""
Violation detectors — SPEC §5.3 and §5.4.

DAY_TRADING (FLAG)
    Per client: if more than 3 distinct ISINs have a Buy followed by a Sell
    within any 24-hour window, flag the client once.

RISK_CONCENTRATION (WARNING)
    Per client: if a single ISIN's market value exceeds 50% of total
    portfolio value, emit one violation per offending ISIN.

Both are pure functions over already-validated domain data. SELL_BEFORE_BUY
and INVALID_VALUE violations are produced elsewhere (FIFO engine and
ingestion validator respectively) — see SPEC §3's violation matrix.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

from src.domain.models import (
    ACTION_BUY,
    ACTION_SELL,
    SEVERITY_FLAG,
    SEVERITY_WARNING,
    VIOLATION_DAY_TRADING,
    VIOLATION_RISK_CONCENTRATION,
    Position,
    ValidatedRow,
    ViolationRecord,
)

DAY_TRADING_PAIR_THRESHOLD: int = 3
DAY_TRADING_WINDOW: datetime.timedelta = datetime.timedelta(hours=24)
RISK_CONCENTRATION_RATIO: Decimal = Decimal("0.5")

ZERO = Decimal(0)


def detect_day_trading(transactions: Iterable[ValidatedRow]) -> list[ViolationRecord]:
    """
    Return one DAY_TRADING violation per client whose trades cross the
    pair-threshold in any rolling 24-hour window.

    A "pair" for window-counting purposes is a distinct ISIN that has both
    a Buy at-or-after the window start and a Sell within the window. This
    follows SPEC §5.3: "count of distinct ISINs where a Sell also exists in
    [t.timestamp, window_end]". The window is anchored at each Buy in turn.
    """
    by_client: dict[str, list[ValidatedRow]] = defaultdict(list)
    for tx in transactions:
        by_client[tx.client_id].append(tx)

    violations: list[ViolationRecord] = []
    for client_id, txs in sorted(by_client.items()):
        txs_sorted = sorted(txs, key=lambda r: (r.timestamp, r.row_number))
        breach = _first_day_trading_breach(txs_sorted)
        if breach is not None:
            anchor_ts, isins = breach
            violations.append(_day_trading_violation(client_id, anchor_ts, isins))
    return violations


def _first_day_trading_breach(
    txs_sorted: list[ValidatedRow],
) -> tuple[datetime.datetime, set[str]] | None:
    """
    Return `(anchor_ts, isins)` for the first Buy whose 24-hour window
    contains sells on more than `DAY_TRADING_PAIR_THRESHOLD` distinct ISINs,
    or None if the client never breaches the threshold.

    Anchoring on each Buy in turn matches SPEC §5.3 — the rolling 24h window
    starts at a Buy and looks forward.
    """
    for anchor in txs_sorted:
        if anchor.action != ACTION_BUY:
            continue
        isins = _sells_in_window(
            txs_sorted, anchor.timestamp, anchor.timestamp + DAY_TRADING_WINDOW
        )
        if len(isins) > DAY_TRADING_PAIR_THRESHOLD:
            return anchor.timestamp, isins
    return None


def _sells_in_window(
    txs: list[ValidatedRow],
    window_start: datetime.datetime,
    window_end: datetime.datetime,
) -> set[str]:
    """Distinct ISINs with a Sell transaction in `[window_start, window_end]`."""
    return {
        tx.isin
        for tx in txs
        if tx.action == ACTION_SELL and window_start <= tx.timestamp <= window_end
    }


def _day_trading_violation(
    client_id: str, anchor_ts: datetime.datetime, isins: set[str]
) -> ViolationRecord:
    return ViolationRecord(
        client_id=client_id,
        violation_type=VIOLATION_DAY_TRADING,
        severity=SEVERITY_FLAG,
        description=(
            f"Client {client_id} traded {len(isins)} "
            f"distinct ISINs within 24h starting at {anchor_ts.isoformat()} "
            f"(threshold: > {DAY_TRADING_PAIR_THRESHOLD})"
        ),
    )


def detect_risk_concentration(positions: Iterable[Position]) -> list[ViolationRecord]:
    """
    For each client, emit one RISK_CONCENTRATION violation per ISIN whose
    market value (`quantity * last_price`) exceeds half the total portfolio
    market value.

    Position rows with `quantity == 0` (fully closed positions) contribute
    nothing to market value and therefore can't be flagged. Clients whose
    total portfolio market value is zero are skipped entirely (no
    meaningful concentration to compute).
    """
    by_client: dict[str, list[Position]] = defaultdict(list)
    for pos in positions:
        by_client[pos.client_id].append(pos)

    violations: list[ViolationRecord] = []
    for client_id, client_positions in sorted(by_client.items()):
        market_values: list[tuple[Position, Decimal]] = [
            (p, p.quantity * p.last_price) for p in client_positions
        ]
        total_value = sum((mv for _, mv in market_values), ZERO)
        if total_value <= 0:
            continue

        for pos, mv in market_values:
            if mv <= 0:
                continue
            ratio = mv / total_value
            if ratio > RISK_CONCENTRATION_RATIO:
                pct = (ratio * 100).quantize(Decimal("0.01"))
                violations.append(
                    ViolationRecord(
                        client_id=client_id,
                        isin=pos.isin,
                        violation_type=VIOLATION_RISK_CONCENTRATION,
                        severity=SEVERITY_WARNING,
                        description=(
                            f"Client {client_id} holds {pct}% of portfolio in {pos.isin} "
                            f"(threshold: > {int(RISK_CONCENTRATION_RATIO * 100)}%)"
                        ),
                    )
                )

    return violations
