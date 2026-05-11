"""
Helpers for `src/api/routes/upload.py` — request guard + domain-to-DB
row converters. Split out so the route file contains only the endpoint.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, UploadFile, status

from src.domain.models import (
    ClientAnalyticsData,
    Position,
    ValidatedRow,
    ViolationRecord,
)

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB — SPEC §0 / §4


async def read_and_guard_file(file: UploadFile) -> bytes:
    """
    Validate the filename, read the body, and enforce empty/size guards.

    No MIME-type check: browsers and curl alike send `application/octet-stream`
    for files of unknown type, so a strict allow-list would lock out legitimate
    uploads, and a permissive allow-list (the previous approach) accepted
    almost anything — strictly worse than no check, because it *looks* like a
    security gate. The `.xlsx` filename check is a cheap smoke filter;
    openpyxl is the real validator (it raises `HeaderValidationError` if the
    bytes aren't a readable workbook).
    """
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Expected an .xlsx file",
        )
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Uploaded file is empty",
        )
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"File exceeds the {MAX_FILE_BYTES // (1024 * 1024)}MB limit",
        )
    return content


def validated_row_to_tx(row: ValidatedRow, upload_id: int) -> dict[str, Any]:
    return {
        "upload_id": upload_id,
        "transaction_id": row.transaction_id,
        "client_id": row.client_id,
        "isin": row.isin,
        "action": row.action,
        "quantity": row.quantity,
        "price": row.price,
        "timestamp": row.timestamp,
    }


def position_to_row(pos: Position, upload_id: int) -> dict[str, Any]:
    return {
        "upload_id": upload_id,
        "client_id": pos.client_id,
        "isin": pos.isin,
        "quantity": pos.quantity,
        "avg_cost": pos.avg_cost,
        "realized_pnl": pos.realized_pnl,
        "unrealized_pnl": pos.unrealized_pnl,
        "last_price": pos.last_price,
    }


def violation_to_row(v: ViolationRecord, upload_id: int) -> dict[str, Any]:
    return {
        "upload_id": upload_id,
        "transaction_id": v.transaction_id,
        "client_id": v.client_id,
        "isin": v.isin,
        "violation_type": v.violation_type,
        "severity": v.severity,
        "description": v.description,
    }


def client_analytics_to_row(ca: ClientAnalyticsData, upload_id: int) -> dict[str, Any]:
    return {
        "upload_id": upload_id,
        "client_id": ca.client_id,
        "avg_holding_days": ca.avg_holding_days,
        "max_portfolio_value": ca.max_portfolio_value,
        "min_portfolio_value": ca.min_portfolio_value,
        "value_range": ca.value_range,
        "winning_trades": ca.winning_trades,
        "total_trades": ca.total_trades,
    }
