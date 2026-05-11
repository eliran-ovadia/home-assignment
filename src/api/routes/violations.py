"""`GET /api/v1/violations` — filterable by `client_id` and `violation_type`."""

from __future__ import annotations

from fastapi import APIRouter

from src.api.deps import CurrentUserDep, SessionDep
from src.api.schemas import ViolationResponse
from src.db.repositories import violations as violations_repo

router = APIRouter()


@router.get("/violations", response_model=list[ViolationResponse])
async def list_violations(
    user: CurrentUserDep,
    session: SessionDep,
    client_id: str | None = None,
    violation_type: str | None = None,
) -> list[ViolationResponse]:
    """All violations in the user's selected upload, optionally narrowed."""
    if user.last_viewed_upload_id is None:
        return []
    rows = await violations_repo.get_by_upload(
        session,
        upload_id=user.last_viewed_upload_id,
        client_id=client_id,
        violation_type=violation_type,
    )
    return [ViolationResponse.model_validate(row) for row in rows]
