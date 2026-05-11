"""
`GET /api/v1/uploads` and `PUT /api/v1/users/me/last-viewed`.

Uploads are a shared pool (ADR 016); the `is_last_viewed` flag in each
history item is computed against the *current user's*
`users.last_viewed_upload_id`, so two users browsing the same list see
their own preferences highlighted.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.api.deps import CurrentUserDep, SessionDep
from src.api.schemas import (
    SetLastViewedRequest,
    UploadHistoryItem,
    UploadResponse,
    UploadSummary,
)
from src.db.repositories import positions as positions_repo
from src.db.repositories import uploads as uploads_repo
from src.db.repositories import users as users_repo

router = APIRouter()


@router.get("/uploads", response_model=list[UploadHistoryItem])
async def list_uploads(user: CurrentUserDep, session: SessionDep) -> list[UploadHistoryItem]:
    """Every upload in the system, newest first, with per-user is_last_viewed flag."""
    rows = await uploads_repo.get_all(session)
    return [
        UploadHistoryItem(
            id=row.id,
            filename=row.filename,
            row_count=row.row_count,
            violation_count=row.violation_count,
            uploaded_at=row.uploaded_at,
            is_last_viewed=(row.id == user.last_viewed_upload_id),
        )
        for row in rows
    ]


@router.put(
    "/users/me/last-viewed",
    response_model=UploadResponse,
    responses={404: {"description": "Upload not found"}},
)
async def set_last_viewed(
    body: SetLastViewedRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> UploadResponse:
    """
    Switch the user's preferred upload. No pipeline re-run — the response
    shape mirrors `POST /upload-transactions` so the frontend can swap one
    handler for the other.
    """
    upload = await uploads_repo.get_by_id(session, body.upload_id)
    if upload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Upload {body.upload_id} not found",
        )

    await users_repo.update_last_viewed(session, user_id=user.id, upload_id=body.upload_id)
    await session.commit()

    # `transactions_loaded` and `violations_detected` are already denormalised
    # on the upload row at insert time — no need to re-count from the
    # transactions or violations tables. Position count is the only number we
    # actually have to query, and we use COUNT(*) instead of fetching every
    # row.
    positions_computed = await positions_repo.count_by_upload(session, body.upload_id)

    return UploadResponse(
        upload_id=upload.id,
        summary=UploadSummary(
            transactions_loaded=upload.row_count,
            positions_computed=positions_computed,
            violations_detected=upload.violation_count,
        ),
    )
