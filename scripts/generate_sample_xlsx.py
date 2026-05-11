"""
Generate sample .xlsx files for manual testing of `POST /api/v1/upload-transactions`.

Run from the repo root:

    python scripts/generate_sample_xlsx.py

Output: `samples/*.xlsx`. Re-running overwrites the directory. The script is
checked in so the file set can be regenerated or extended; the produced .xlsx
files are also checked in (small, binary, but stable).

File naming
-----------
    01-06   Valid uploads — distinguished by which business-rule violations
            they intentionally trigger (none / SELL_BEFORE_BUY / DAY_TRADING /
            RISK_CONCENTRATION / INVALID_VALUE × 2).
    10-15   Invalid uploads — structural problems that still reject the file
            (missing column, bad action, non-numeric, missing field, mixed,
            empty body). Non-positive quantity/price is *not* in this group —
            per the assignment's Part D rule matrix it surfaces as an
            INVALID_VALUE violation on a successful upload.

The numbers (01- vs 10-) keep valid and invalid files visually grouped in
file managers and IDE trees.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook

HEADER_ROW: list[str] = [
    "ClientId",
    "TransactionId",
    "ISIN",
    "Action",
    "Quantity",
    "Price",
    "Timestamp",
]

OUT_DIR = Path(__file__).resolve().parent.parent / "samples"
OUT_DIR.mkdir(exist_ok=True)


def _ts(day: int, hour: int = 9, minute: int = 0) -> datetime.datetime:
    """Concise timestamp builder. All sample data is in January 2026."""
    return datetime.datetime(2026, 1, day, hour, minute)


def _build(filename: str, rows: list[list[Any]], *, header: list[str] | None = None) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(header if header is not None else HEADER_ROW)
    for row in rows:
        worksheet.append(row)
    path = OUT_DIR / filename
    workbook.save(path)
    print(f"  wrote {path.relative_to(OUT_DIR.parent)}")


# ── Valid uploads ────────────────────────────────────────────────────────────

# 01 — Clean: multiple clients + ISINs, one completed trade, two open positions,
# zero business-rule violations.
_build(
    "01_valid_clean.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy", 100, 150.00, _ts(1)],  # Apple buy
        ["C001", "TXN002", "US0378331005", "Sell", 100, 160.00, _ts(5)],  # Apple sell — +$1000
        ["C002", "TXN003", "US5949181045", "Buy", 50, 300.00, _ts(2)],  # MSFT buy, holds
        ["C002", "TXN004", "US0378331005", "Buy", 50, 155.00, _ts(4)],  # AAPL buy, holds
        ["C003", "TXN005", "US02079K3059", "Buy", 20, 1500.00, _ts(3)],  # GOOG buy
        ["C003", "TXN006", "US02079K3059", "Sell", 10, 1600.00, _ts(7)],  # partial GOOG sell
    ],
)

# 02 — Triggers SELL_BEFORE_BUY: C002 sells an ISIN it never bought.
_build(
    "02_violation_sell_before_buy.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy", 100, 150.00, _ts(1)],
        ["C001", "TXN002", "US0378331005", "Sell", 100, 160.00, _ts(2)],
        ["C002", "TXN003", "US0378331005", "Sell", 50, 155.00, _ts(3)],  # ← no prior buy
    ],
)

# 03 — Triggers DAY_TRADING: 4 distinct same-ISIN buy/sell pairs inside a 24h
# window. SPEC §5.3 fires at > 3 pairs, so 4 is the smallest case that flags.
_build(
    "03_violation_day_trading.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy", 100, 150.00, _ts(1, 9, 0)],
        ["C001", "TXN002", "US0378331005", "Sell", 100, 152.00, _ts(1, 10, 0)],
        ["C001", "TXN003", "US5949181045", "Buy", 50, 300.00, _ts(1, 11, 0)],
        ["C001", "TXN004", "US5949181045", "Sell", 50, 305.00, _ts(1, 12, 0)],
        ["C001", "TXN005", "US02079K3059", "Buy", 20, 1500.00, _ts(1, 13, 0)],
        ["C001", "TXN006", "US02079K3059", "Sell", 20, 1510.00, _ts(1, 14, 0)],
        ["C001", "TXN007", "US88160R1014", "Buy", 10, 250.00, _ts(1, 15, 0)],
        ["C001", "TXN008", "US88160R1014", "Sell", 10, 255.00, _ts(1, 16, 0)],
    ],
)

# 04 — Triggers RISK_CONCENTRATION: AAPL ends at ~91% of C001's market value.
_build(
    "04_violation_risk_concentration.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy", 1000, 100.00, _ts(1)],  # AAPL  = 100,000
        ["C001", "TXN002", "US5949181045", "Buy", 100, 100.00, _ts(2)],  # MSFT  =  10,000
    ],
)

# 05 — Triggers INVALID_VALUE: a Sell row with negative quantity. The file
# still uploads — assignment Part D classifies non-positive qty/price as a
# violation (severity ERROR), not as a reason to reject the upload. The bad
# row lands in the transactions table for audit but is skipped from FIFO,
# so no bogus position appears.
_build(
    "05_violation_invalid_negative_quantity.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy", 100, 150.00, _ts(1)],
        ["C001", "TXN002", "US0378331005", "Sell", -50, 160.00, _ts(2)],  # ← qty < 0
    ],
)

# 06 — Triggers INVALID_VALUE: a Buy row with negative price. Same handling as 05.
# (Rule is strictly `< 0` per assignment Part D, so 0 is permitted; this uses -50.)
_build(
    "06_violation_invalid_negative_price.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy", 100, -50.00, _ts(1)],
    ],
)


# ── Invalid uploads (structural validation errors → 422, nothing saved) ──────

# 10 — Missing a required column entirely (Timestamp).
_build(
    "10_invalid_missing_column.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy", 100, 150.00],
    ],
    header=["ClientId", "TransactionId", "ISIN", "Action", "Quantity", "Price"],
)

# 11 — Action value outside the {Buy, Sell} domain.
_build(
    "11_invalid_bad_action.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Transfer", 100, 150.00, _ts(1)],
    ],
)

# 12 — Non-numeric value in the Quantity column (a string).
_build(
    "12_invalid_text_in_quantity.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy", "many", 150.00, _ts(1)],
    ],
)

# 13 — Missing required field (client_id is blank on a single row).
_build(
    "13_invalid_missing_field.xlsx",
    [
        [None, "TXN001", "US0378331005", "Buy", 100, 150.00, _ts(1)],
    ],
)

# 14 — Multiple rows, each with a different *structural* error. (Non-positive
# qty/price is intentionally NOT included here — those are INVALID_VALUE
# violations, not upload-blocking errors.)
_build(
    "14_invalid_multiple_errors.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy", 100, 150.00, _ts(1)],  # OK
        ["C002", "TXN002", "US0378331005", "HOLD", 50, 160.00, _ts(2)],  # bad action
        ["C003", "TXN003", "US5949181045", "Buy", "ten", 300.00, _ts(2)],  # qty is text
        [None, "TXN004", "US02079K3059", "Buy", 20, 100.00, _ts(3)],  # missing client_id
    ],
)

# 15 — Header row only, no data rows.
_build("15_empty_data_rows.xlsx", [])

print(f"\nWrote {len(list(OUT_DIR.glob('*.xlsx')))} files to {OUT_DIR.relative_to(Path.cwd())}/")
