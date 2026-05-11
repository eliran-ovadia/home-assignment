"""
`POST /api/v1/upload-transactions` — the upload pipeline.

Flow (all inside one DB transaction once we reach the bulk-insert step):
  1. Guard the request (size limit, file extension/content-type).
  2. Parse the workbook bytes into `RawRow`s — CPU-bound, off the event loop.
  3. Validate every row — also CPU-bound.
     • Any errors → return 422 with the rejected_rows list. Nothing written.
  4. Run the FIFO engine and the two violation detectors — CPU-bound.
  5. Compute per-client analytics — CPU-bound.
  6. Begin DB transaction:
        a. Insert the `uploads` row → get `upload_id`.
        b. Bulk-insert transactions / positions / violations / client_analytics.
        c. Update `users.last_viewed_upload_id` for the current user.
     Commit. If any of (a-c) raises, the whole transaction rolls back and
     the DB is unchanged.
  7. Return the upload summary.

All CPU-bound steps are pushed to a thread via `asyncio.to_thread` so the
event loop keeps serving GET requests during a long parse.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from src.api.deps import CurrentUserDep, SessionDep
from src.api.schemas import (
    RejectedRow,
    RejectedRowsResponse,
    UploadResponse,
    UploadSummary,
)
from src.db.repositories import client_analytics as client_analytics_repo
from src.db.repositories import positions as positions_repo
from src.db.repositories import transactions as transactions_repo
from src.db.repositories import uploads as uploads_repo
from src.db.repositories import users as users_repo
from src.db.repositories import violations as violations_repo
from src.domain.analytics import compute_client_analytics
from src.domain.fifo import run_fifo
from src.domain.models import (
    ClientAnalyticsData,
    Position,
    ValidatedRow,
    ViolationRecord,
)
from src.domain.violations import detect_day_trading, detect_risk_concentration
from src.ingestion.parser import HeaderValidationError, parse_workbook
from src.ingestion.validator import validate_rows

router = APIRouter()

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB — SPEC §0 / §4
_XLSX_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/octet-stream",  # some browsers send this; trust the extension instead
    }
)


@router.post(
    "/upload-transactions",
    response_model=UploadResponse,
    responses={
        400: {"description": "Missing or malformed session token"},
        422: {"model": RejectedRowsResponse, "description": "File or row validation failed"},
    },
)
async def upload_transactions(
    user: CurrentUserDep,
    session: SessionDep,
    file: UploadFile = File(...),  # noqa: B008 — File(...) at the default is the FastAPI idiom
) -> UploadResponse | JSONResponse:
    """Ingest an .xlsx file end-to-end and persist the results atomically."""
    content = await _read_and_guard_file(file)

    # CPU-bound steps off the event loop. Parser + validator + FIFO + analytics
    # are all pure Python with no async-aware libraries; the thread offload
    # keeps GET requests responsive during a long upload.
    try:
        raw_rows = await asyncio.to_thread(parse_workbook, content)
    except HeaderValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    valid_rows, row_errors = await asyncio.to_thread(validate_rows, raw_rows)
    if row_errors:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=RejectedRowsResponse(
                rejected_rows=[
                    RejectedRow(
                        row_number=e.row_number,
                        transaction_id=e.transaction_id,
                        column=e.column,
                        reason=e.reason,
                    )
                    for e in row_errors
                ]
            ).model_dump(),
        )

    if not valid_rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Workbook contains a header row but no data rows",
        )

    fifo_result = await asyncio.to_thread(run_fifo, valid_rows)
    day_trading = await asyncio.to_thread(detect_day_trading, valid_rows)
    risk_concentration = await asyncio.to_thread(detect_risk_concentration, fifo_result.positions)
    client_analytics = await asyncio.to_thread(
        compute_client_analytics, valid_rows, fifo_result.completed_trades
    )

    all_violations = list(fifo_result.sell_before_buy_violations) + day_trading + risk_concentration

    # Single DB transaction. Any failure rolls everything back (the
    # AsyncSession dependency rolls back on exception by default).
    upload_row = await uploads_repo.insert(
        session,
        filename=file.filename or "upload.xlsx",
        file_content=content,
        row_count=len(valid_rows),
        violation_count=len(all_violations),
    )
    upload_id = upload_row.id

    await transactions_repo.bulk_insert(
        session, [_validated_row_to_tx(row, upload_id) for row in valid_rows]
    )
    await positions_repo.bulk_insert(
        session, [_position_to_row(pos, upload_id) for pos in fifo_result.positions]
    )
    await client_analytics_repo.bulk_insert(
        session, [_client_analytics_to_row(ca, upload_id) for ca in client_analytics]
    )
    await violations_repo.bulk_insert(
        session, [_violation_to_row(v, upload_id) for v in all_violations]
    )
    await users_repo.update_last_viewed(session, user_id=user.id, upload_id=upload_id)
    await session.commit()

    return UploadResponse(
        upload_id=upload_id,
        summary=UploadSummary(
            transactions_loaded=len(valid_rows),
            positions_computed=len(fifo_result.positions),
            violations_detected=len(all_violations),
        ),
    )


# ── helpers ──────────────────────────────────────────────────────────────────


async def _read_and_guard_file(file: UploadFile) -> bytes:
    """Validate filename + content-type, read the body, enforce the size cap."""
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expected an .xlsx file",
        )
    if file.content_type and file.content_type not in _XLSX_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unexpected content type: {file.content_type}",
        )
    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File exceeds the {MAX_FILE_BYTES // (1024 * 1024)}MB limit",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty",
        )
    return content


def _validated_row_to_tx(row: ValidatedRow, upload_id: int) -> dict[str, Any]:
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


def _position_to_row(pos: Position, upload_id: int) -> dict[str, Any]:
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


def _violation_to_row(v: ViolationRecord, upload_id: int) -> dict[str, Any]:
    return {
        "upload_id": upload_id,
        "transaction_id": v.transaction_id,
        "client_id": v.client_id,
        "isin": v.isin,
        "violation_type": v.violation_type,
        "severity": v.severity,
        "description": v.description,
    }


def _client_analytics_to_row(ca: ClientAnalyticsData, upload_id: int) -> dict[str, Any]:
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
