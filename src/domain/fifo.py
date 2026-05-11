"""
FIFO cost-basis engine — SPEC §5.2.

Operates on `ValidatedRow`s grouped by `(client_id, isin)`. For each group:
  - Buys append a lot to a per-pair deque.
  - Sells consume lots from the front (oldest first). Each matched portion
    emits a `CompletedTrade`. A Sell with no open lots (or a partial match)
    emits a `SELL_BEFORE_BUY` violation for the un-matched quantity and is
    skipped — no short positions are ever created.

After all transactions process, each `(client, isin)` yields one `Position`
with `quantity` (sum of remaining lots), `avg_cost` (cost-weighted average
of remaining lots), `realized_pnl` (running sum across all sells), and
`unrealized_pnl` (last observed price minus avg_cost, times quantity).

`last_price` is determined per ISIN across the *whole upload* — the latest
transaction's price for that ISIN, regardless of which client traded it.

Per-pair state lives in `_PairFIFO`; the module-level `run_fifo` is purely
orchestration — group, dispatch, aggregate.
"""

from __future__ import annotations

import datetime
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from src.domain.models import (
    ACTION_BUY,
    ACTION_SELL,
    SEVERITY_ERROR,
    VIOLATION_SELL_BEFORE_BUY,
    CompletedTrade,
    FIFOResult,
    Position,
    ValidatedRow,
    ViolationRecord,
)

ZERO = Decimal(0)


@dataclass(slots=True)
class _Lot:
    """Single open buy lot in the FIFO deque. `quantity` mutates as sells consume it."""

    quantity: Decimal
    price: Decimal
    timestamp: datetime.datetime

    def __post_init__(self) -> None:
        # Defensive — should never happen because the validator filters non-positive.
        if self.quantity <= 0:
            raise ValueError("Lot quantity must be positive")


@dataclass(slots=True)
class _PairFIFO:
    """
    Per-(client, ISIN) FIFO state and operations.

    Each transaction in the pair is fed in via `apply(tx)`; at the end the
    caller asks `to_position(last_price)` for the final `Position`. The
    `completed_trades` and `violations` lists are populated incrementally
    as sells consume lots.
    """

    client_id: str
    isin: str
    lots: deque[_Lot] = field(default_factory=deque)
    realized_pnl: Decimal = ZERO
    completed_trades: list[CompletedTrade] = field(default_factory=list)
    violations: list[ViolationRecord] = field(default_factory=list)

    def apply(self, tx: ValidatedRow) -> None:
        """Process one transaction. Dispatches on `tx.action`."""
        if tx.action == ACTION_BUY:
            self._apply_buy(tx)
        elif tx.action == ACTION_SELL:
            self._apply_sell(tx)
        else:
            # Defensive: validator only emits ACTION_BUY / ACTION_SELL.
            raise ValueError(f"Unknown action {tx.action!r} on row {tx.row_number}")

    def to_position(self, last_price: Decimal) -> Position:
        """Build the final `Position` for this pair, marked to *last_price*."""
        quantity, avg_cost = _summarize_open_lots(self.lots)
        unrealized = (last_price - avg_cost) * quantity if quantity > 0 else ZERO
        return Position(
            client_id=self.client_id,
            isin=self.isin,
            quantity=quantity,
            avg_cost=avg_cost,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=unrealized,
            last_price=last_price,
        )

    # ── internals ────────────────────────────────────────────────────────────

    def _apply_buy(self, tx: ValidatedRow) -> None:
        self.lots.append(_Lot(quantity=tx.quantity, price=tx.price, timestamp=tx.timestamp))

    def _apply_sell(self, tx: ValidatedRow) -> None:
        remaining = tx.quantity
        while remaining > 0 and self.lots:
            remaining = self._consume_oldest_lot(tx, remaining)
        if remaining > 0:
            self.violations.append(self._sell_before_buy(tx, remaining))

    def _consume_oldest_lot(self, tx: ValidatedRow, remaining: Decimal) -> Decimal:
        """Match *remaining* against the front lot; return the new remaining quantity."""
        lot = self.lots[0]
        matched = min(remaining, lot.quantity)
        self.realized_pnl += matched * (tx.price - lot.price)
        self.completed_trades.append(
            CompletedTrade(
                client_id=self.client_id,
                isin=self.isin,
                quantity=matched,
                buy_price=lot.price,
                sell_price=tx.price,
                buy_timestamp=lot.timestamp,
                sell_timestamp=tx.timestamp,
            )
        )
        lot.quantity -= matched
        if lot.quantity == 0:
            self.lots.popleft()
        return remaining - matched

    def _sell_before_buy(self, tx: ValidatedRow, unmatched: Decimal) -> ViolationRecord:
        return ViolationRecord(
            client_id=self.client_id,
            isin=self.isin,
            transaction_id=tx.transaction_id,
            violation_type=VIOLATION_SELL_BEFORE_BUY,
            severity=SEVERITY_ERROR,
            description=(
                f"Client {self.client_id} attempted to sell {unmatched} "
                f"units of {self.isin} with no open position"
            ),
        )


def run_fifo(transactions: Iterable[ValidatedRow]) -> FIFOResult:
    """
    Run the FIFO pipeline over all validated transactions in one upload.

    Returns a `FIFOResult` containing one `Position` per `(client, isin)`
    pair, every `CompletedTrade` produced, and any `SELL_BEFORE_BUY`
    violations encountered.
    """
    transactions = list(transactions)
    last_prices = _compute_last_prices(transactions)
    groups = _group_and_sort(transactions)

    positions: list[Position] = []
    completed_trades: list[CompletedTrade] = []
    violations: list[ViolationRecord] = []

    for (client_id, isin), group_txs in sorted(groups.items()):
        processor = _PairFIFO(client_id=client_id, isin=isin)
        for tx in group_txs:
            processor.apply(tx)
        positions.append(processor.to_position(last_prices.get(isin, ZERO)))
        completed_trades.extend(processor.completed_trades)
        violations.extend(processor.violations)

    return FIFOResult(
        positions=positions,
        completed_trades=completed_trades,
        sell_before_buy_violations=violations,
    )


def _group_and_sort(
    transactions: list[ValidatedRow],
) -> dict[tuple[str, str], list[ValidatedRow]]:
    """
    Group transactions by (client_id, isin) and sort each group by
    (timestamp, row_number).

    The per-group sort is a *correctness* requirement — FIFO must process
    transactions in chronological order. The caller in `run_fifo` then
    iterates `sorted(groups.items())`, which is a *determinism* convenience
    (stable test output, predictable violation ordering) rather than a
    correctness requirement: each `(client, isin)` pair is independent of
    every other, so processing order between pairs cannot change the result.
    """
    groups: dict[tuple[str, str], list[ValidatedRow]] = {}
    for tx in transactions:
        groups.setdefault((tx.client_id, tx.isin), []).append(tx)
    for group in groups.values():
        group.sort(key=lambda r: (r.timestamp, r.row_number))
    return groups


def _compute_last_prices(transactions: list[ValidatedRow]) -> dict[str, Decimal]:
    """Per-ISIN price of the latest transaction in the whole upload."""
    # isin → (ts, row_number, price); tie-break on row_number for stable order.
    last: dict[str, tuple[datetime.datetime, int, Decimal]] = {}
    for tx in transactions:
        existing = last.get(tx.isin)
        if existing is None or (tx.timestamp, tx.row_number) > (existing[0], existing[1]):
            last[tx.isin] = (tx.timestamp, tx.row_number, tx.price)
    return {isin: price for isin, (_, _, price) in last.items()}


def _summarize_open_lots(lots: deque[_Lot]) -> tuple[Decimal, Decimal]:
    """Return (total_quantity, weighted_avg_cost). Both zero for an empty deque."""
    total_qty = ZERO
    total_cost = ZERO
    for lot in lots:
        total_qty += lot.quantity
        total_cost += lot.quantity * lot.price
    if total_qty == 0:
        return ZERO, ZERO
    return total_qty, total_cost / total_qty
