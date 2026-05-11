"""Unit tests for `src.domain.analytics`. Pure functions — no DB, no I/O."""

from __future__ import annotations

import datetime
from decimal import Decimal

from src.domain.analytics import compute_client_analytics
from src.domain.models import CompletedTrade, ValidatedRow


def _tx(
    row_number: int,
    *,
    client_id: str = "C001",
    isin: str = "ISIN_A",
    action: str = "Buy",
    quantity: int | str = 10,
    price: int | str = 100,
    hour: int = 9,
    day: int = 1,
) -> ValidatedRow:
    return ValidatedRow(
        row_number=row_number,
        transaction_id=f"TXN{row_number:03d}",
        client_id=client_id,
        isin=isin,
        action=action,
        quantity=Decimal(str(quantity)),
        price=Decimal(str(price)),
        timestamp=datetime.datetime(2026, 1, day, hour, 0),
    )


def _completed(
    client_id: str,
    *,
    isin: str = "ISIN_A",
    quantity: int = 10,
    buy_price: int = 100,
    sell_price: int = 120,
    buy_day: int = 1,
    sell_day: int = 5,
) -> CompletedTrade:
    return CompletedTrade(
        client_id=client_id,
        isin=isin,
        quantity=Decimal(quantity),
        buy_price=Decimal(buy_price),
        sell_price=Decimal(sell_price),
        buy_timestamp=datetime.datetime(2026, 1, buy_day, 9, 0),
        sell_timestamp=datetime.datetime(2026, 1, sell_day, 9, 0),
    )


def _for(rows, client_id: str):
    for row in rows:
        if row.client_id == client_id:
            return row
    raise AssertionError(f"No analytics row for {client_id}")


# ── portfolio-value simulation ───────────────────────────────────────────────


def test_buy_only_client_has_zero_value_range() -> None:
    """
    SPEC §5.5: portfolio values are observed *after every transaction*, not
    before. A client who buys $1000 and holds (no further transactions)
    has exactly one observation = $1000 → range = 0. This is the spec-
    correct behaviour; a synthetic pre-trade zero baseline would (wrongly)
    yield range = $1000 here.
    """
    result = compute_client_analytics(
        [_tx(1, action="Buy", quantity=10, price=100)],
        [],
    )
    row = _for(result, "C001")
    assert row.max_portfolio_value == Decimal(1000)
    assert row.min_portfolio_value == Decimal(1000)
    assert row.value_range == Decimal(0)


def test_buy_then_sell_back_to_zero_records_full_swing() -> None:
    """Client buys 10@100 (value 1000), then sells 10@120 (value 0). Range = 1000."""
    result = compute_client_analytics(
        [
            _tx(1, action="Buy", quantity=10, price=100, hour=9),
            _tx(2, action="Sell", quantity=10, price=120, hour=10),
        ],
        [],
    )
    row = _for(result, "C001")
    assert row.max_portfolio_value == Decimal(1000)
    assert row.min_portfolio_value == Decimal(0)
    assert row.value_range == Decimal(1000)


def test_market_price_moves_propagate_across_clients() -> None:
    """
    Client A buys 10@100; later client B trades same ISIN at 200. A's
    portfolio gets marked to 200 even though A never traded again — the
    cross-client price move is what makes A appear in the simulation.
    """
    result = compute_client_analytics(
        [
            _tx(1, client_id="C_A", action="Buy", quantity=10, price=100, hour=9),
            _tx(2, client_id="C_B", action="Buy", quantity=5, price=200, hour=10),
        ],
        [],
    )
    row_a = _for(result, "C_A")
    # A's first observation is post-tx-1: holdings = 10 @ last_price 100 → 1000.
    # A's second observation is post-tx-2: holdings = 10 @ new last_price 200 → 2000.
    assert row_a.min_portfolio_value == Decimal(1000)
    assert row_a.max_portfolio_value == Decimal(2000)
    assert row_a.value_range == Decimal(1000)


def test_holdings_sum_across_isins() -> None:
    """A client holding multiple ISINs is valued at qty×price summed over all."""
    result = compute_client_analytics(
        [
            _tx(1, isin="ISIN_A", action="Buy", quantity=10, price=100, hour=9),
            _tx(2, isin="ISIN_B", action="Buy", quantity=5, price=50, hour=10),
        ],
        [],
    )
    row = _for(result, "C001")
    # First observation: 10 × 100 = 1000.
    # Second observation: (10 × 100) + (5 × 50) = 1250.
    assert row.min_portfolio_value == Decimal(1000)
    assert row.max_portfolio_value == Decimal(1250)
    assert row.value_range == Decimal(250)


def test_oversell_does_not_create_short_holding() -> None:
    """A Sell that exceeds current holdings only consumes the matched portion."""
    result = compute_client_analytics(
        [
            _tx(1, action="Buy", quantity=5, price=100, hour=9),
            _tx(2, action="Sell", quantity=999, price=100, hour=10),  # oversell
        ],
        [],
    )
    row = _for(result, "C001")
    # Post-buy: 500. Post-sell: 0 (only matched 5 units, no short).
    assert row.min_portfolio_value == Decimal(0)
    assert row.max_portfolio_value == Decimal(500)


# ── completed-trade stats ────────────────────────────────────────────────────


def test_client_with_no_completed_trades_has_none_stats() -> None:
    """avg_holding_days / winning_trades / total_trades are all None when no trades."""
    result = compute_client_analytics(
        [_tx(1, action="Buy", quantity=10, price=100)],
        [],  # no completed trades
    )
    row = _for(result, "C001")
    assert row.avg_holding_days is None
    assert row.winning_trades is None
    assert row.total_trades is None


def test_winning_and_losing_trades_counted_separately() -> None:
    """winning_trades counts trades with sell_price > buy_price; total counts all."""
    result = compute_client_analytics(
        [_tx(1, action="Buy", quantity=1, price=1, hour=9)],
        [
            _completed("C001", buy_price=100, sell_price=120, buy_day=1, sell_day=2),  # win
            _completed("C001", buy_price=100, sell_price=80, buy_day=3, sell_day=4),  # loss
            _completed("C001", buy_price=100, sell_price=110, buy_day=5, sell_day=7),  # win
        ],
    )
    row = _for(result, "C001")
    assert row.total_trades == 3
    assert row.winning_trades == 2


def test_avg_holding_days_is_mean_across_trades() -> None:
    """avg_holding_days = mean of (sell_ts - buy_ts).days for each trade."""
    result = compute_client_analytics(
        [_tx(1, action="Buy", quantity=1, price=1, hour=9)],
        [
            _completed("C001", buy_day=1, sell_day=3),  # 2 days
            _completed("C001", buy_day=1, sell_day=5),  # 4 days
            _completed("C001", buy_day=1, sell_day=7),  # 6 days
        ],
    )
    row = _for(result, "C001")
    assert row.avg_holding_days == Decimal(4)  # (2 + 4 + 6) / 3


def test_completed_trades_grouped_by_client() -> None:
    """Trades for client A do not bleed into client B's stats."""
    result = compute_client_analytics(
        [
            _tx(1, client_id="C_A", action="Buy", quantity=1, price=1),
            _tx(2, client_id="C_B", action="Buy", quantity=1, price=1),
        ],
        [
            _completed("C_A", buy_price=100, sell_price=120),  # A wins
            _completed("C_A", buy_price=100, sell_price=120),  # A wins
            _completed("C_B", buy_price=100, sell_price=80),  # B loses
        ],
    )
    row_a = _for(result, "C_A")
    row_b = _for(result, "C_B")
    assert (row_a.total_trades, row_a.winning_trades) == (2, 2)
    assert (row_b.total_trades, row_b.winning_trades) == (1, 0)


def test_empty_transactions_returns_empty_list() -> None:
    """No transactions → no clients → empty analytics list (no synthetic rows)."""
    assert compute_client_analytics([], []) == []


def test_clients_returned_in_alphabetical_order() -> None:
    """Output order is sorted by client_id — deterministic regardless of input order."""
    result = compute_client_analytics(
        [
            _tx(1, client_id="C_Z", action="Buy", quantity=1, price=1),
            _tx(2, client_id="C_A", action="Buy", quantity=1, price=1),
            _tx(3, client_id="C_M", action="Buy", quantity=1, price=1),
        ],
        [],
    )
    assert [row.client_id for row in result] == ["C_A", "C_M", "C_Z"]
