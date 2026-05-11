"""
Per-client analytics produced at upload time — SPEC §5.5.

`compute_client_analytics` walks every transaction in the upload once and
emits one `ClientAnalyticsData` per client. Output drives the
`client_analytics` table and three of the analytics-endpoint fields:
`avg_holding_time_per_client`, `most_volatile_client`, and
`win_rate_per_client`.

Portfolio-value simulation rule (SPEC §5.5): "for each client, simulate
portfolio value after every transaction (using last known price per ISIN
at that timestamp). value_range = max(values) - min(values)." We process
all transactions globally in time order so an ISIN's price moves with the
market — a later trade by client B updates the last_price used to revalue
client A's existing holdings.

Quantity bookkeeping mirrors FIFO semantics: a Sell that exceeds the
client's current holding contributes only the matched portion to the
quantity update (an over-sell does not create a short position).

Code shape: the public `compute_client_analytics` is purely orchestration.
Each step is a small helper with a single responsibility:
  - `_simulate_portfolio_extremes` — the time-ordered min/max walk
  - `_apply_to_holdings` — one transaction's effect on one client's holdings
  - `_group_trades_by_client` — bucket the completed trades
  - `_compute_trade_stats` — holding-days + win-rate stats for one client
  - `_build_client_analytics` — assemble one `ClientAnalyticsData` row
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from src.domain.models import (
    ACTION_BUY,
    ClientAnalyticsData,
    CompletedTrade,
    ValidatedRow,
)

ZERO = Decimal(0)


def compute_client_analytics(
    transactions: Iterable[ValidatedRow],
    completed_trades: Iterable[CompletedTrade],
) -> list[ClientAnalyticsData]:
    """
    Produce one `ClientAnalyticsData` row per client that appears in *transactions*.

    Clients with no `CompletedTrade` records leave `avg_holding_days`,
    `winning_trades`, and `total_trades` as None — they have open positions
    only, or no successful Buy→Sell matches yet.
    """
    transactions = list(transactions)
    completed_trades = list(completed_trades)

    clients: set[str] = {tx.client_id for tx in transactions}
    portfolio_extremes = _simulate_portfolio_extremes(transactions, clients)
    trades_by_client = _group_trades_by_client(completed_trades)

    return [
        _build_client_analytics(
            client_id=client_id,
            extremes=portfolio_extremes[client_id],
            client_trades=trades_by_client.get(client_id, []),
        )
        for client_id in sorted(clients)
    ]


# ── helpers ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Extremes:
    """Lowest and highest portfolio value observed for one client."""

    min_value: Decimal
    max_value: Decimal


@dataclass(frozen=True, slots=True)
class _TradeStats:
    """Holding-time + win-rate stats for one client. All three are None when no completed trades."""

    avg_holding_days: Decimal | None
    winning_trades: int | None
    total_trades: int | None


def _simulate_portfolio_extremes(
    transactions: list[ValidatedRow], clients: set[str]
) -> dict[str, _Extremes]:
    """
    Walk *transactions* in global time order and track every client's
    min/max portfolio value as the market evolves.

    "Market evolves" matters: when client B trades ISIN X, the new price is
    used to revalue client A's existing X holdings on that same timestamp.
    This is what makes the simulation reflect a shared market rather than
    each client living in their own price world.
    """
    holdings: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    last_prices: dict[str, Decimal] = {}
    min_value = dict.fromkeys(clients, ZERO)
    max_value = dict.fromkeys(clients, ZERO)

    for tx in sorted(transactions, key=lambda r: (r.timestamp, r.row_number)):
        _apply_to_holdings(holdings[tx.client_id], tx)
        last_prices[tx.isin] = tx.price

        for client_id in clients:
            value = _portfolio_value(holdings.get(client_id, {}), last_prices)
            if value < min_value[client_id]:
                min_value[client_id] = value
            if value > max_value[client_id]:
                max_value[client_id] = value

    return {c: _Extremes(min_value=min_value[c], max_value=max_value[c]) for c in clients}


def _apply_to_holdings(holdings: dict[str, Decimal], tx: ValidatedRow) -> None:
    """
    Update one client's per-ISIN holdings for one transaction.

    Buys add. Sells subtract only the matched portion (FIFO semantics —
    over-sells do not create short positions). Holdings can therefore reach
    zero but never go negative.
    """
    if tx.action == ACTION_BUY:
        holdings[tx.isin] += tx.quantity
        return
    current = holdings[tx.isin]
    matched = min(tx.quantity, current) if current > 0 else ZERO
    holdings[tx.isin] = current - matched


def _portfolio_value(holdings: dict[str, Decimal], last_prices: dict[str, Decimal]) -> Decimal:
    """Sum `quantity × last_price` over every ISIN with positive quantity."""
    total = ZERO
    for isin, qty in holdings.items():
        if qty > 0:
            total += qty * last_prices.get(isin, ZERO)
    return total


def _group_trades_by_client(
    completed_trades: list[CompletedTrade],
) -> dict[str, list[CompletedTrade]]:
    grouped: dict[str, list[CompletedTrade]] = defaultdict(list)
    for trade in completed_trades:
        grouped[trade.client_id].append(trade)
    return grouped


def _compute_trade_stats(client_trades: list[CompletedTrade]) -> _TradeStats:
    """
    Holding-days mean + win/total counts for one client. Returns a
    three-None `_TradeStats` if the client has no completed trades.
    """
    if not client_trades:
        return _TradeStats(avg_holding_days=None, winning_trades=None, total_trades=None)
    holding_days = [
        Decimal((trade.sell_timestamp - trade.buy_timestamp).days) for trade in client_trades
    ]
    return _TradeStats(
        avg_holding_days=sum(holding_days, ZERO) / Decimal(len(holding_days)),
        winning_trades=sum(1 for t in client_trades if t.is_winning),
        total_trades=len(client_trades),
    )


def _build_client_analytics(
    *,
    client_id: str,
    extremes: _Extremes,
    client_trades: list[CompletedTrade],
) -> ClientAnalyticsData:
    """Assemble a single `ClientAnalyticsData` row from its constituent pieces."""
    stats = _compute_trade_stats(client_trades)
    return ClientAnalyticsData(
        client_id=client_id,
        max_portfolio_value=extremes.max_value,
        min_portfolio_value=extremes.min_value,
        value_range=extremes.max_value - extremes.min_value,
        avg_holding_days=stats.avg_holding_days,
        winning_trades=stats.winning_trades,
        total_trades=stats.total_trades,
    )
