"""
Generate sample .xlsx files for manual testing of `POST /api/v1/upload-transactions`.

Run from the repo root:

    python scripts/generate_sample_xlsx.py

Output: `samples/*.xlsx`. Re-running overwrites the directory. The script is
checked in so the file set can be regenerated or extended; the produced .xlsx
files are also checked in (small, binary, but stable).

File naming
-----------
    01-04   Valid uploads — distinguished by which business-rule violations
            they intentionally trigger (none / SELL_BEFORE_BUY / DAY_TRADING /
            RISK_CONCENTRATION).
    10-17   Invalid uploads — every row-level validation error in SPEC §5.1,
            plus structural problems (missing column, empty body).

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
        ["C001", "TXN001", "US0378331005", "Buy",  100, 150.00, _ts(1)],   # Apple buy
        ["C001", "TXN002", "US0378331005", "Sell", 100, 160.00, _ts(5)],   # Apple sell — +$1000
        ["C002", "TXN003", "US5949181045", "Buy",  50,  300.00, _ts(2)],   # MSFT buy, holds
        ["C002", "TXN004", "US0378331005", "Buy",  50,  155.00, _ts(4)],   # AAPL buy, holds
        ["C003", "TXN005", "US02079K3059", "Buy",  20,  1500.00, _ts(3)],  # GOOG buy
        ["C003", "TXN006", "US02079K3059", "Sell", 10,  1600.00, _ts(7)],  # partial GOOG sell
    ],
)

# 02 — Triggers SELL_BEFORE_BUY: C002 sells an ISIN it never bought.
_build(
    "02_violation_sell_before_buy.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy",  100, 150.00, _ts(1)],
        ["C001", "TXN002", "US0378331005", "Sell", 100, 160.00, _ts(2)],
        ["C002", "TXN003", "US0378331005", "Sell", 50,  155.00, _ts(3)],   # ← no prior buy
    ],
)

# 03 — Triggers DAY_TRADING: 4 distinct same-ISIN buy/sell pairs inside a 24h
# window. SPEC §5.3 fires at > 3 pairs, so 4 is the smallest case that flags.
_build(
    "03_violation_day_trading.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy",  100, 150.00, _ts(1, 9,  0)],
        ["C001", "TXN002", "US0378331005", "Sell", 100, 152.00, _ts(1, 10, 0)],
        ["C001", "TXN003", "US5949181045", "Buy",  50,  300.00, _ts(1, 11, 0)],
        ["C001", "TXN004", "US5949181045", "Sell", 50,  305.00, _ts(1, 12, 0)],
        ["C001", "TXN005", "US02079K3059", "Buy",  20,  1500.00, _ts(1, 13, 0)],
        ["C001", "TXN006", "US02079K3059", "Sell", 20,  1510.00, _ts(1, 14, 0)],
        ["C001", "TXN007", "US88160R1014", "Buy",  10,  250.00, _ts(1, 15, 0)],
        ["C001", "TXN008", "US88160R1014", "Sell", 10,  255.00, _ts(1, 16, 0)],
    ],
)

# 04 — Triggers RISK_CONCENTRATION: AAPL ends at ~91% of C001's market value.
_build(
    "04_violation_risk_concentration.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy", 1000, 100.00, _ts(1)],   # AAPL  = 100,000
        ["C001", "TXN002", "US5949181045", "Buy", 100,  100.00, _ts(2)],   # MSFT  =  10,000
    ],
)


# ── Invalid uploads (validation errors → 422, nothing saved) ─────────────────

# 10 — Missing a required column entirely (Timestamp).
_build(
    "10_invalid_missing_column.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy", 100, 150.00],
    ],
    header=["ClientId", "TransactionId", "ISIN", "Action", "Quantity", "Price"],
)

# 11 — Negative quantity on a Sell row.
_build(
    "11_invalid_negative_quantity.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy",  100, 150.00, _ts(1)],
        ["C001", "TXN002", "US0378331005", "Sell", -50, 160.00, _ts(2)],   # ← qty < 0
    ],
)

# 12 — Zero price (spec requires strictly > 0).
_build(
    "12_invalid_zero_price.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy", 100, 0.00, _ts(1)],
    ],
)

# 13 — Action value outside the {Buy, Sell} domain.
_build(
    "13_invalid_bad_action.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Transfer", 100, 150.00, _ts(1)],
    ],
)

# 14 — Non-numeric value in the Quantity column (a string).
_build(
    "14_invalid_text_in_quantity.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy", "many", 150.00, _ts(1)],
    ],
)

# 15 — Missing required field (client_id is blank on a single row).
_build(
    "15_invalid_missing_field.xlsx",
    [
        [None, "TXN001", "US0378331005", "Buy", 100, 150.00, _ts(1)],
    ],
)

# 16 — Multiple rows, each with a different error. Lets you see the per-row
# error table in the UI populated with several distinct reasons at once.
_build(
    "16_invalid_multiple_errors.xlsx",
    [
        ["C001", "TXN001", "US0378331005", "Buy",   100,    150.00, _ts(1)],   # OK
        ["C002", "TXN002", "US0378331005", "Sell",  -10,    160.00, _ts(2)],   # neg qty
        ["C003", "TXN003", "US5949181045", "HOLD",  50,     300.00, _ts(2)],   # bad action
        ["C004", "TXN004", "US02079K3059", "Buy",   20,     -100.00, _ts(3)],  # neg price
        ["C005", "TXN005", "US88160R1014", "Buy",   "ten",  250.00, _ts(4)],   # qty is text
    ],
)

# 17 — Header row only, no data rows.
_build("17_empty_data_rows.xlsx", [])

print(f"\nWrote {len(list(OUT_DIR.glob('*.xlsx')))} files to {OUT_DIR.relative_to(Path.cwd())}/")
