"""Unit tests for `src.ingestion.validator`. Pure functions — no DB, no I/O."""

from __future__ import annotations

import datetime
from decimal import Decimal

from src.domain.models import RawRow
from src.ingestion.validator import validate_rows


def _row(row_number: int = 2, **overrides: object) -> RawRow:
    """A RawRow with defaults that pass validation, override fields as needed."""
    defaults: dict[str, object] = {
        "transaction_id": "TXN001",
        "client_id": "C001",
        "isin": "US0378331005",
        "action": "Buy",
        "quantity": 10,
        "price": 100,
        "timestamp": datetime.datetime(2026, 1, 1, 9, 30),
    }
    defaults.update(overrides)
    return RawRow(row_number=row_number, **defaults)  # type: ignore[arg-type]


def test_valid_row_passes_through() -> None:
    valid, errors = validate_rows([_row()])
    assert errors == []
    assert len(valid) == 1
    only = valid[0]
    assert only.transaction_id == "TXN001"
    assert only.action == "Buy"
    assert only.quantity == Decimal(10)
    assert only.price == Decimal(100)


def test_whitespace_is_stripped_and_action_titlecased() -> None:
    valid, errors = validate_rows(
        [_row(transaction_id="  TXN001  ", client_id=" C001 ", isin=" US0378 ", action=" buy ")]
    )
    assert errors == []
    only = valid[0]
    assert only.transaction_id == "TXN001"
    assert only.client_id == "C001"
    assert only.isin == "US0378"
    assert only.action == "Buy"


def test_quantity_zero_is_rejected() -> None:
    valid, errors = validate_rows([_row(quantity=0)])
    assert valid == []
    assert len(errors) == 1
    assert errors[0].column == "quantity"
    assert "positive" in errors[0].reason


def test_quantity_negative_is_rejected() -> None:
    _, errors = validate_rows([_row(quantity=-5)])
    assert any(e.column == "quantity" and "positive" in e.reason for e in errors)


def test_price_negative_is_rejected() -> None:
    _, errors = validate_rows([_row(price=Decimal("-3.50"))])
    assert any(e.column == "price" and "positive" in e.reason for e in errors)


def test_price_zero_is_rejected() -> None:
    _, errors = validate_rows([_row(price=0)])
    assert any(e.column == "price" for e in errors)


def test_string_in_quantity_column_is_rejected() -> None:
    _, errors = validate_rows([_row(quantity="abc")])
    assert any(e.column == "quantity" and "number" in e.reason for e in errors)


def test_invalid_action_is_rejected() -> None:
    valid, errors = validate_rows([_row(action="HOLD")])
    assert valid == []
    assert any(e.column == "action" for e in errors)


def test_missing_required_field_is_rejected() -> None:
    valid, errors = validate_rows([_row(client_id=None)])
    assert valid == []
    assert any(e.column == "client_id" and "Missing" in e.reason for e in errors)


def test_empty_string_field_is_rejected() -> None:
    _, errors = validate_rows([_row(transaction_id="   ")])
    assert any(e.column == "transaction_id" and "Missing" in e.reason for e in errors)


def test_non_datetime_timestamp_is_rejected() -> None:
    _, errors = validate_rows([_row(timestamp="2026-01-01")])  # string, not datetime
    assert any(e.column == "timestamp" for e in errors)


def test_tz_aware_timestamp_is_normalized_to_naive_utc() -> None:
    tz_tokyo = datetime.timezone(datetime.timedelta(hours=9))
    tokyo_ts = datetime.datetime(2026, 1, 1, 18, 30, tzinfo=tz_tokyo)
    valid, errors = validate_rows([_row(timestamp=tokyo_ts)])
    assert errors == []
    assert valid[0].timestamp.tzinfo is None
    assert valid[0].timestamp == datetime.datetime(2026, 1, 1, 9, 30)


def test_bool_in_quantity_is_rejected() -> None:
    # True would coerce to 1 if we used Decimal blindly — guard against it.
    _, errors = validate_rows([_row(quantity=True)])
    assert any(e.column == "quantity" for e in errors)


def test_row_number_propagates_to_error() -> None:
    _, errors = validate_rows([_row(row_number=42, quantity=-1)])
    assert errors[0].row_number == 42


def test_transaction_id_propagates_to_error() -> None:
    _, errors = validate_rows([_row(transaction_id="TXN999", quantity=-1)])
    assert errors[0].transaction_id == "TXN999"


def test_one_row_can_yield_multiple_errors() -> None:
    _, errors = validate_rows([_row(quantity=-1, price=-2, action="HOLD")])
    columns = {e.column for e in errors}
    assert {"quantity", "price", "action"}.issubset(columns)


def test_mixed_valid_and_invalid_rows() -> None:
    valid, errors = validate_rows([_row(row_number=2), _row(row_number=3, quantity=-1)])
    assert len(valid) == 1
    assert valid[0].row_number == 2
    assert len(errors) == 1
    assert errors[0].row_number == 3
