"""Unit tests for `src.domain.violations`. Pure functions — no DB, no I/O."""

from __future__ import annotations

import datetime
from decimal import Decimal

from src.domain.models import (
    SEVERITY_ERROR,
    VIOLATION_DAY_TRADING,
    VIOLATION_INVALID_VALUE,
    VIOLATION_RISK_CONCENTRATION,
    Position,
    ValidatedRow,
)
from src.domain.violations import (
    detect_day_trading,
    detect_invalid_values,
    detect_risk_concentration,
)


def _tx(
    row_number: int,
    *,
    client_id: str = "C001",
    isin: str = "ISIN_A",
    action: str = "Buy",
    hour: int = 0,
    day: int = 1,
) -> ValidatedRow:
    return ValidatedRow(
        row_number=row_number,
        transaction_id=f"TXN{row_number:03d}",
        client_id=client_id,
        isin=isin,
        action=action,
        quantity=Decimal(10),
        price=Decimal(100),
        timestamp=datetime.datetime(2026, 1, day, hour, 0),
    )


# ── Invalid-value detector ───────────────────────────────────────────────────


def _tx_with(
    row_number: int,
    *,
    quantity: Decimal | int = 10,
    price: Decimal | int = 100,
    client_id: str = "C001",
) -> ValidatedRow:
    return ValidatedRow(
        row_number=row_number,
        transaction_id=f"TXN{row_number:03d}",
        client_id=client_id,
        isin="ISIN_A",
        action="Buy",
        quantity=Decimal(quantity),
        price=Decimal(price),
        timestamp=datetime.datetime(2026, 1, 1, 9, 0),
    )


def test_invalid_values_negative_price_flagged_and_row_excluded() -> None:
    rows = [_tx_with(1), _tx_with(2, price=-10)]
    eligible, violations = detect_invalid_values(rows)
    assert [r.row_number for r in eligible] == [1]
    assert len(violations) == 1
    v = violations[0]
    assert v.violation_type == VIOLATION_INVALID_VALUE
    assert v.severity == SEVERITY_ERROR
    assert v.transaction_id == "TXN002"
    assert "price=-10" in v.description


def test_invalid_values_zero_is_allowed() -> None:
    """Assignment rule is strictly `< 0`; zero is permitted (e.g. free shares)."""
    eligible, violations = detect_invalid_values([_tx_with(1, quantity=0, price=0)])
    assert len(eligible) == 1
    assert violations == []


def test_invalid_values_negative_quantity_flagged_and_row_excluded() -> None:
    rows = [_tx_with(1, quantity=-5)]
    eligible, violations = detect_invalid_values(rows)
    assert eligible == []
    assert len(violations) == 1
    assert "quantity=-5" in violations[0].description


def test_invalid_values_both_fields_bad_yields_single_violation() -> None:
    """One row with two bad fields emits one violation listing both — not two."""
    rows = [_tx_with(1, quantity=-1, price=-2)]
    _, violations = detect_invalid_values(rows)
    assert len(violations) == 1
    desc = violations[0].description
    assert "quantity=-1" in desc and "price=-2" in desc


def test_invalid_values_preserves_order_for_eligible_rows() -> None:
    rows = [_tx_with(1), _tx_with(2, quantity=-3), _tx_with(3), _tx_with(4, price=-1)]
    eligible, violations = detect_invalid_values(rows)
    assert [r.row_number for r in eligible] == [1, 3]
    assert [v.transaction_id for v in violations] == ["TXN002", "TXN004"]


def test_invalid_values_empty_input_returns_empty_lists() -> None:
    eligible, violations = detect_invalid_values([])
    assert eligible == []
    assert violations == []


# ── Day-trading detector ──────────────────────────────────────────────────────


def test_day_trading_four_distinct_pairs_in_24h_flags_client() -> None:
    """Buy + Sell of 4 distinct ISINs within 24h → DAY_TRADING (threshold is >3)."""
    transactions: list[ValidatedRow] = []
    rn = 1
    for isin in ("ISIN_A", "ISIN_B", "ISIN_C", "ISIN_D"):
        transactions.append(_tx(rn, isin=isin, action="Buy", hour=9))
        rn += 1
        transactions.append(_tx(rn, isin=isin, action="Sell", hour=10))
        rn += 1

    violations = detect_day_trading(transactions)
    assert len(violations) == 1
    assert violations[0].client_id == "C001"
    assert violations[0].violation_type == VIOLATION_DAY_TRADING


def test_day_trading_three_pairs_does_not_flag() -> None:
    """Exactly 3 distinct ISINs in 24h → not flagged (rule is strictly > 3)."""
    transactions: list[ValidatedRow] = []
    rn = 1
    for isin in ("ISIN_A", "ISIN_B", "ISIN_C"):
        transactions.append(_tx(rn, isin=isin, action="Buy", hour=9))
        rn += 1
        transactions.append(_tx(rn, isin=isin, action="Sell", hour=10))
        rn += 1

    assert detect_day_trading(transactions) == []


def test_day_trading_pairs_outside_24h_window_do_not_count() -> None:
    """Sells on different calendar days don't aggregate into one 24h window."""
    transactions: list[ValidatedRow] = []
    rn = 1
    # Each pair is its own day at hour 9 / 10 → 4 distinct ISINs, but each
    # buy's 24h window only contains its own sell.
    for day, isin in enumerate(("ISIN_A", "ISIN_B", "ISIN_C", "ISIN_D"), start=1):
        transactions.append(_tx(rn, isin=isin, action="Buy", hour=9, day=day * 2))
        rn += 1
        transactions.append(_tx(rn, isin=isin, action="Sell", hour=10, day=day * 2))
        rn += 1

    assert detect_day_trading(transactions) == []


def test_day_trading_flag_is_per_client() -> None:
    """Two clients can each independently breach the threshold."""
    transactions: list[ValidatedRow] = []
    rn = 1
    for client in ("C_A", "C_B"):
        for isin in ("ISIN_A", "ISIN_B", "ISIN_C", "ISIN_D"):
            transactions.append(_tx(rn, client_id=client, isin=isin, action="Buy", hour=9))
            rn += 1
            transactions.append(_tx(rn, client_id=client, isin=isin, action="Sell", hour=10))
            rn += 1

    violations = detect_day_trading(transactions)
    flagged_clients = {v.client_id for v in violations}
    assert flagged_clients == {"C_A", "C_B"}


def test_day_trading_emits_at_most_one_violation_per_client() -> None:
    """Even if many anchor buys would each see >3 pairs, only one violation per client."""
    # Generate 5 ISINs × buy+sell within the same 24h window — many anchors,
    # but we should only get one violation per client.
    transactions: list[ValidatedRow] = []
    rn = 1
    for isin in ("A", "B", "C", "D", "E"):
        transactions.append(_tx(rn, isin=f"ISIN_{isin}", action="Buy", hour=9))
        rn += 1
        transactions.append(_tx(rn, isin=f"ISIN_{isin}", action="Sell", hour=10))
        rn += 1

    violations = detect_day_trading(transactions)
    assert len(violations) == 1


def test_day_trading_sells_without_matching_buy_do_not_count_as_pairs() -> None:
    """
    SPEC §5.3 (clarified): a pair requires BOTH a Buy and a Sell of the same
    ISIN in the window. A client who buys A and then sells B/C/D/E (without
    ever buying B/C/D/E in this upload) is misbehaving — those sells will
    surface as SELL_BEFORE_BUY violations from the FIFO engine — but they
    are NOT day-trading pairs and must not flag DAY_TRADING.
    """
    transactions: list[ValidatedRow] = [
        _tx(1, isin="ISIN_A", action="Buy", hour=9),  # anchor
        _tx(2, isin="ISIN_B", action="Sell", hour=10),
        _tx(3, isin="ISIN_C", action="Sell", hour=10),
        _tx(4, isin="ISIN_D", action="Sell", hour=10),
        _tx(5, isin="ISIN_E", action="Sell", hour=10),
    ]
    assert detect_day_trading(transactions) == []


# ── Risk-concentration detector ───────────────────────────────────────────────


def _pos(client_id: str, isin: str, quantity: int, last_price: int) -> Position:
    return Position(
        client_id=client_id,
        isin=isin,
        quantity=Decimal(quantity),
        avg_cost=Decimal(last_price),  # value irrelevant for concentration
        realized_pnl=Decimal(0),
        unrealized_pnl=Decimal(0),
        last_price=Decimal(last_price),
    )


def test_risk_concentration_above_threshold_flags_isin() -> None:
    """One ISIN at 60% of portfolio market value → RISK_CONCENTRATION."""
    positions = [
        _pos("C001", "ISIN_A", quantity=60, last_price=100),  # 6000
        _pos("C001", "ISIN_B", quantity=40, last_price=100),  # 4000
    ]
    violations = detect_risk_concentration(positions)
    assert len(violations) == 1
    assert violations[0].violation_type == VIOLATION_RISK_CONCENTRATION
    assert violations[0].isin == "ISIN_A"
    assert violations[0].client_id == "C001"


def test_risk_concentration_exactly_at_threshold_does_not_flag() -> None:
    """50% is the boundary — rule is strictly > 50%, equal does not flag."""
    positions = [
        _pos("C001", "ISIN_A", quantity=50, last_price=100),  # 5000
        _pos("C001", "ISIN_B", quantity=50, last_price=100),  # 5000
    ]
    assert detect_risk_concentration(positions) == []


def test_risk_concentration_below_threshold_does_not_flag() -> None:
    positions = [
        _pos("C001", "ISIN_A", quantity=40, last_price=100),  # 4000
        _pos("C001", "ISIN_B", quantity=30, last_price=100),  # 3000
        _pos("C001", "ISIN_C", quantity=30, last_price=100),  # 3000
    ]
    assert detect_risk_concentration(positions) == []


def test_risk_concentration_is_per_client() -> None:
    positions = [
        _pos("C_A", "ISIN_A", quantity=80, last_price=100),  # 80% — flag
        _pos("C_A", "ISIN_B", quantity=20, last_price=100),
        _pos("C_B", "ISIN_A", quantity=40, last_price=100),  # 40% — no flag
        _pos("C_B", "ISIN_B", quantity=60, last_price=100),  # 60% — flag
    ]
    violations = detect_risk_concentration(positions)
    flagged = {(v.client_id, v.isin) for v in violations}
    assert flagged == {("C_A", "ISIN_A"), ("C_B", "ISIN_B")}


def test_risk_concentration_zero_portfolio_skipped() -> None:
    """A client with no open positions can't be concentrated in anything."""
    positions = [_pos("C001", "ISIN_A", quantity=0, last_price=100)]
    assert detect_risk_concentration(positions) == []


def test_risk_concentration_emits_per_offending_isin() -> None:
    """If two ISINs each independently > 50% (impossible under a single client, but
    we still verify the loop emits one violation per qualifying ISIN — the >50%
    rule means at most one qualifies in practice)."""
    positions = [
        _pos("C001", "ISIN_A", quantity=70, last_price=100),  # 70% — flag
        _pos("C001", "ISIN_B", quantity=30, last_price=100),
    ]
    violations = detect_risk_concentration(positions)
    assert len(violations) == 1
    assert violations[0].isin == "ISIN_A"
