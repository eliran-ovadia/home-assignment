"""Unit tests for `src.domain.fifo`. Pure functions — no DB, no I/O."""

from __future__ import annotations

import datetime
from decimal import Decimal

from src.domain.fifo import run_fifo
from src.domain.models import VIOLATION_SELL_BEFORE_BUY, ValidatedRow


def _tx(
    row_number: int,
    *,
    client_id: str = "C001",
    isin: str = "ISIN_A",
    action: str = "Buy",
    quantity: int | str = 10,
    price: int | str = 100,
    hour: int = 0,
) -> ValidatedRow:
    return ValidatedRow(
        row_number=row_number,
        transaction_id=f"TXN{row_number:03d}",
        client_id=client_id,
        isin=isin,
        action=action,
        quantity=Decimal(str(quantity)),
        price=Decimal(str(price)),
        timestamp=datetime.datetime(2026, 1, 1, hour, 0),
    )


def _position_for(result, client_id: str, isin: str):
    for pos in result.positions:
        if pos.client_id == client_id and pos.isin == isin:
            return pos
    raise AssertionError(f"No position found for ({client_id}, {isin})")


def test_basic_buy_then_full_sell_realizes_pnl() -> None:
    result = run_fifo(
        [
            _tx(1, action="Buy", quantity=10, price=100, hour=9),
            _tx(2, action="Sell", quantity=10, price=120, hour=10),
        ]
    )
    pos = _position_for(result, "C001", "ISIN_A")
    assert pos.quantity == Decimal(0)
    assert pos.realized_pnl == Decimal(200)  # 10 * (120 - 100)
    assert len(result.completed_trades) == 1
    trade = result.completed_trades[0]
    assert trade.quantity == Decimal(10)
    assert trade.buy_price == Decimal(100)
    assert trade.sell_price == Decimal(120)


def test_fifo_ordering_consumes_oldest_lot_first() -> None:
    # Two buy lots at different prices, then one sell that consumes the older lot only.
    result = run_fifo(
        [
            _tx(1, action="Buy", quantity=10, price=100, hour=9),
            _tx(2, action="Buy", quantity=10, price=200, hour=10),
            _tx(3, action="Sell", quantity=5, price=150, hour=11),
        ]
    )
    pos = _position_for(result, "C001", "ISIN_A")
    # Sold 5 at $150 from the $100 lot → realized = 5 * 50 = 250.
    assert pos.realized_pnl == Decimal(250)
    # Remaining: 5 at $100 + 10 at $200 → 15 units, avg cost = (500 + 2000) / 15.
    assert pos.quantity == Decimal(15)
    assert pos.avg_cost == (Decimal(500) + Decimal(2000)) / Decimal(15)


def test_partial_sell_spanning_two_lots() -> None:
    result = run_fifo(
        [
            _tx(1, action="Buy", quantity=10, price=100, hour=9),
            _tx(2, action="Buy", quantity=10, price=200, hour=10),
            _tx(3, action="Sell", quantity=15, price=300, hour=11),
        ]
    )
    pos = _position_for(result, "C001", "ISIN_A")
    # 10 sold from $100 lot → 10 * 200 = 2000
    # 5 sold from $200 lot → 5 * 100 = 500
    assert pos.realized_pnl == Decimal(2500)
    assert pos.quantity == Decimal(5)
    assert pos.avg_cost == Decimal(200)
    # Two completed trades emitted (one per matched portion).
    assert len(result.completed_trades) == 2


def test_oversell_emits_violation_and_does_not_short() -> None:
    result = run_fifo(
        [
            _tx(1, action="Buy", quantity=5, price=100, hour=9),
            _tx(2, action="Sell", quantity=8, price=120, hour=10),
        ]
    )
    pos = _position_for(result, "C001", "ISIN_A")
    # Only 5 matched — 5 * (120 - 100) = 100. Remaining quantity must be 0 (no short).
    assert pos.realized_pnl == Decimal(100)
    assert pos.quantity == Decimal(0)
    assert pos.unrealized_pnl == Decimal(0)
    # One SELL_BEFORE_BUY violation for the un-matched 3 units.
    assert len(result.sell_before_buy_violations) == 1
    violation = result.sell_before_buy_violations[0]
    assert violation.violation_type == VIOLATION_SELL_BEFORE_BUY
    assert "3" in violation.description


def test_sell_with_empty_queue_emits_violation_and_no_position_change() -> None:
    result = run_fifo([_tx(1, action="Sell", quantity=10, price=100, hour=9)])
    pos = _position_for(result, "C001", "ISIN_A")
    assert pos.quantity == Decimal(0)
    assert pos.realized_pnl == Decimal(0)
    assert len(result.completed_trades) == 0
    assert len(result.sell_before_buy_violations) == 1


def test_buy_only_produces_unrealized_pnl() -> None:
    # Buy at $100, last observed price for this ISIN is the same $100 (no other tx).
    result = run_fifo([_tx(1, action="Buy", quantity=10, price=100, hour=9)])
    pos = _position_for(result, "C001", "ISIN_A")
    assert pos.quantity == Decimal(10)
    assert pos.avg_cost == Decimal(100)
    assert pos.realized_pnl == Decimal(0)
    assert pos.unrealized_pnl == Decimal(0)  # last_price == avg_cost
    assert pos.last_price == Decimal(100)


def test_last_price_propagates_across_clients_in_same_isin() -> None:
    # Client A buys at $100; client B then trades the same ISIN at $200.
    # A's unrealized P&L should mark to B's $200.
    result = run_fifo(
        [
            _tx(1, client_id="C_A", action="Buy", quantity=10, price=100, hour=9),
            _tx(2, client_id="C_B", action="Buy", quantity=5, price=200, hour=10),
        ]
    )
    pos_a = _position_for(result, "C_A", "ISIN_A")
    assert pos_a.last_price == Decimal(200)
    assert pos_a.unrealized_pnl == Decimal(10) * (Decimal(200) - Decimal(100))


def test_multi_client_independence() -> None:
    # Each client's FIFO queue is its own — a buy by C_B does not affect C_A.
    result = run_fifo(
        [
            _tx(1, client_id="C_A", action="Buy", quantity=10, price=100, hour=9),
            _tx(2, client_id="C_B", action="Buy", quantity=10, price=100, hour=9),
            _tx(3, client_id="C_A", action="Sell", quantity=10, price=150, hour=10),
        ]
    )
    pos_a = _position_for(result, "C_A", "ISIN_A")
    pos_b = _position_for(result, "C_B", "ISIN_A")
    assert pos_a.realized_pnl == Decimal(500)
    assert pos_a.quantity == Decimal(0)
    assert pos_b.realized_pnl == Decimal(0)
    assert pos_b.quantity == Decimal(10)


def test_completed_trades_record_correct_pair_details() -> None:
    buy_time = datetime.datetime(2026, 1, 1, 9, 0)
    sell_time = datetime.datetime(2026, 1, 2, 9, 0)
    result = run_fifo(
        [
            ValidatedRow(
                row_number=1,
                transaction_id="TXN001",
                client_id="C001",
                isin="ISIN_A",
                action="Buy",
                quantity=Decimal(10),
                price=Decimal(100),
                timestamp=buy_time,
            ),
            ValidatedRow(
                row_number=2,
                transaction_id="TXN002",
                client_id="C001",
                isin="ISIN_A",
                action="Sell",
                quantity=Decimal(10),
                price=Decimal(120),
                timestamp=sell_time,
            ),
        ]
    )
    assert len(result.completed_trades) == 1
    trade = result.completed_trades[0]
    assert trade.client_id == "C001"
    assert trade.isin == "ISIN_A"
    assert trade.buy_timestamp == buy_time
    assert trade.sell_timestamp == sell_time
    assert trade.is_winning is True
    assert trade.realized_pnl == Decimal(200)
