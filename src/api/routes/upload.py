"""
`POST /api/v1/upload-transactions` — the upload pipeline.

Flow (all inside one DB transaction once we reach the bulk-insert step):
  1. Guard the request (size limit, file extension/content-type).
  2. Parse the workbook bytes into `RawRow`s — CPU-bound, off the event loop.
  3. Validate every row's structure — also CPU-bound.
     • Any structural error → return 422 with the rejected_rows list. Nothing
       written. (Structural = wrong type, missing column/field, bad action.)
  4. Partition rows by value validity. Rows with quantity < 0 or price < 0
     become INVALID_VALUE violations (severity ERROR) but the upload still
     proceeds — they're persisted to `transactions` for audit and excluded
     from FIFO/analytics. This matches the assignment's Part D rule matrix
     (zero is permitted; the rule is strictly less-than).
  5. Run the FIFO engine and the violation detectors — CPU-bound.
  6. Compute per-client analytics — CPU-bound.
  7. Begin DB transaction:
        a. Insert the `uploads` row → get `upload_id`.
        b. Bulk-insert transactions / positions / violations / client_analytics.
        c. Update `users.last_viewed_upload_id` for the current user.
     Commit. If any of (a-c) raises, the whole transaction rolls back and
     the DB is unchanged.
  8. Return the upload summary.

All CPU-bound steps are pushed to a thread via `asyncio.to_thread` so the
event loop keeps serving GET requests during a long parse. Non-endpoint
helpers (file guard, row-shape converters) live in
`src/api/route_helpers/upload.py`.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from src.api.deps import CurrentUserDep, SessionDep
from src.api.route_helpers.upload import (
    client_analytics_to_row,
    position_to_row,
    read_and_guard_file,
    validated_row_to_tx,
    violation_to_row,
)
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
from src.domain.violations import (
    detect_day_trading,
    detect_invalid_values,
    detect_risk_concentration,
)
from src.ingestion.parser import HeaderValidationError, parse_workbook
from src.ingestion.validator import validate_rows

router = APIRouter()


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
    content = await read_and_guard_file(file)

    # CPU-bound steps off the event loop. Parser + validator + FIFO + analytics
    # are all pure Python with no async-aware libraries; the thread offload
    # keeps GET requests responsive during a long upload.
    try:
        raw_rows = await asyncio.to_thread(parse_workbook, content)
    except HeaderValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    valid_rows, row_errors = await asyncio.to_thread(validate_rows, raw_rows)
    if row_errors:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Workbook contains a header row but no data rows",
        )

    # Partition rows by value validity before any domain math touches them.
    # `eligible_rows` is what FIFO / day-trading / analytics see; the original
    # `valid_rows` (eligible + invalid-value) is still what gets persisted to
    # the transactions table for audit. See `detect_invalid_values` docstring.
    eligible_rows, invalid_value_violations = await asyncio.to_thread(
        detect_invalid_values, valid_rows
    )

    fifo_result = await asyncio.to_thread(run_fifo, eligible_rows)
    day_trading = await asyncio.to_thread(detect_day_trading, eligible_rows)
    risk_concentration = await asyncio.to_thread(detect_risk_concentration, fifo_result.positions)
    client_analytics = await asyncio.to_thread(
        compute_client_analytics, eligible_rows, fifo_result.completed_trades
    )

    all_violations = (
        invalid_value_violations
        + list(fifo_result.sell_before_buy_violations)
        + day_trading
        + risk_concentration
    )

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
        session, [validated_row_to_tx(row, upload_id) for row in valid_rows]
    )
    await positions_repo.bulk_insert(
        session, [position_to_row(pos, upload_id) for pos in fifo_result.positions]
    )
    await client_analytics_repo.bulk_insert(
        session, [client_analytics_to_row(ca, upload_id) for ca in client_analytics]
    )
    await violations_repo.bulk_insert(
        session, [violation_to_row(v, upload_id) for v in all_violations]
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
