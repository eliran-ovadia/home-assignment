"""
Row-level validator. Applies the *structural* rules in SPEC §5.1 to every
`RawRow` and returns a split of (valid_rows, errors). The API layer rejects
the whole upload if `errors` is non-empty — see ADR 011.

Scope note: the validator checks **type/shape**, not business values.
A row whose quantity or price is ≤ 0 still passes here; the assignment's
Part D classifies those as INVALID_VALUE business-rule violations to be
flagged in the violations table, not as upload-blocking errors. The
post-validation detector `detect_invalid_values` in `src.domain.violations`
filters those rows out of FIFO / analytics and emits the violation records.

Normalisation done here, in this order, per SPEC §5.1:
  - strip whitespace from every string-typed field
  - title-case `action` (`buy` → `Buy`)
  - convert numeric cells to `Decimal` via `str(value)` to dodge float artifacts
  - treat naïve timestamps as UTC

Code shape: each field validator returns either the normalised value or a
`RowError` (a union, not a tuple — easier to reason about). `_take` routes
the union, accumulating errors and yielding the value (or None) to the
caller. `_validate_one_row` is the single-row orchestrator; `validate_rows`
is just a loop over it.
"""

from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from src.domain.models import (
    ACTION_BUY,
    ACTION_SELL,
    VALID_ACTIONS,
    RawRow,
    RowError,
    ValidatedRow,
)


def validate_rows(rows: list[RawRow]) -> tuple[list[ValidatedRow], list[RowError]]:
    """
    Split *rows* into valid + invalid.

    A single row can contribute multiple `RowError`s (e.g. quantity AND price
    both bad). Any row with at least one error is excluded from `valid_rows`.
    Order of `valid_rows` matches the input order; `errors` is in row order.
    """
    valid_rows: list[ValidatedRow] = []
    errors: list[RowError] = []
    for raw in rows:
        result = _validate_one_row(raw)
        if isinstance(result, ValidatedRow):
            valid_rows.append(result)
        else:
            errors.extend(result)
    return valid_rows, errors


# ── per-row orchestration ────────────────────────────────────────────────────


def _validate_one_row(raw: RawRow) -> ValidatedRow | list[RowError]:
    """
    Validate every field of one row. Returns the typed `ValidatedRow` if
    everything passed, or the accumulated `list[RowError]` if anything failed.
    """
    hint = _hint_transaction_id(raw.transaction_id)
    errs: list[RowError] = []

    transaction_id = _take(errs, _validate_text(raw, "transaction_id", raw.transaction_id, hint))
    client_id = _take(errs, _validate_text(raw, "client_id", raw.client_id, hint))
    isin = _take(errs, _validate_text(raw, "isin", raw.isin, hint))
    action = _take(errs, _validate_action(raw, raw.action, hint))
    quantity = _take(errs, _validate_number(raw, "quantity", raw.quantity, hint))
    price = _take(errs, _validate_number(raw, "price", raw.price, hint))
    timestamp = _take(errs, _validate_timestamp(raw, raw.timestamp, hint))

    if errs:
        return errs

    # `errs` is empty → every `_take` returned a non-None value. The casts
    # turn `T | None` into `T` for the type checker without a runtime check.
    return ValidatedRow(
        row_number=raw.row_number,
        transaction_id=cast(str, transaction_id),
        client_id=cast(str, client_id),
        isin=cast(str, isin),
        action=cast(str, action),
        quantity=cast(Decimal, quantity),
        price=cast(Decimal, price),
        timestamp=cast(datetime.datetime, timestamp),
    )


def _take[T](errors: list[RowError], result: RowError | T) -> T | None:
    """Split a validator's union result: append on error, return value otherwise."""
    if isinstance(result, RowError):
        errors.append(result)
        return None
    return result


def _err(raw: RawRow, hint: str | None, column: str, reason: str) -> RowError:
    """Build a `RowError` with the boilerplate fields filled in from *raw* + *hint*."""
    return RowError(
        row_number=raw.row_number,
        transaction_id=hint,
        column=column,
        reason=reason,
    )


def _hint_transaction_id(raw_value: Any) -> str | None:
    """Best-effort transaction_id surfacing so 422 payloads carry "row 5 (TXN042)…"."""
    if raw_value is None:
        return None
    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        return stripped or None
    return str(raw_value)


# ── field validators ─────────────────────────────────────────────────────────
# Each returns the normalised value on success, or a `RowError` on failure.


def _validate_text(raw: RawRow, field_name: str, value: Any, hint: str | None) -> RowError | str:
    """Required text field: must be non-None and non-empty after stripping."""
    if value is None:
        return _err(raw, hint, field_name, f"Missing required field: {field_name}")
    text = str(value).strip()
    if not text:
        return _err(raw, hint, field_name, f"Missing required field: {field_name}")
    return text


def _validate_action(raw: RawRow, value: Any, hint: str | None) -> RowError | str:
    """Action must be 'Buy' or 'Sell' (case-insensitive on input)."""
    if value is None:
        return _err(raw, hint, "action", "Missing required field: action")
    normalized = str(value).strip().title()
    if normalized not in VALID_ACTIONS:
        return _err(
            raw, hint, "action", f"Expected '{ACTION_BUY}' or '{ACTION_SELL}', got: {value!r}"
        )
    return normalized


def _validate_number(
    raw: RawRow, field_name: str, value: Any, hint: str | None
) -> RowError | Decimal:
    """
    Convert to a finite `Decimal`. Does NOT enforce positivity — that's a
    business-rule check (INVALID_VALUE) handled by `detect_invalid_values`
    in the domain layer, not a structural validation that rejects the upload.
    """
    if value is None:
        return _err(raw, hint, field_name, f"Missing required field: {field_name}")
    if isinstance(value, bool):
        # bool is a subtype of int — guard against `True` slipping through as 1.
        return _err(raw, hint, field_name, f"Expected a number, got: {value!r}")
    try:
        # `str()` avoids float-precision drift, e.g. Decimal(0.1) → 0.10000000000...
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return _err(raw, hint, field_name, f"Expected a number, got: {value!r}")
    if not decimal_value.is_finite():
        return _err(raw, hint, field_name, f"Expected a finite number, got: {value!r}")
    return decimal_value


def _validate_timestamp(raw: RawRow, value: Any, hint: str | None) -> RowError | datetime.datetime:
    """
    Timestamp must be a `datetime` *or* an ISO-8601 string. Tz-aware values
    are normalised to naïve UTC.

    Excel cells formatted as Date/Time arrive as `datetime` objects; cells
    formatted as Text (or files written by tools that don't apply a date
    format) arrive as strings. We accept both shapes so a workbook with
    `"2026-01-01T10:00:00"` text cells doesn't fail the upload — that's the
    shape the assignment's sample file uses.
    """
    if value is None:
        return _err(raw, hint, "timestamp", "Missing required field: timestamp")
    if isinstance(value, str):
        try:
            value = datetime.datetime.fromisoformat(value.strip())
        except ValueError:
            return _err(raw, hint, "timestamp", f"Expected an ISO-8601 datetime, got: {value!r}")
    if not isinstance(value, datetime.datetime):
        return _err(raw, hint, "timestamp", f"Expected a datetime, got: {value!r}")
    if value.tzinfo is not None:
        # Strip the tz after converting to UTC so storage is naïve-UTC.
        value = value.astimezone(datetime.UTC).replace(tzinfo=None)
    return value
