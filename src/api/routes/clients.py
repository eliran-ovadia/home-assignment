"""
`GET /api/v1/clients` and `GET /api/v1/clients/{client_id}/positions`.

Both routes operate on the current user's `last_viewed_upload_id`. A user
who has never selected an upload (and never uploaded — both paths set
`last_viewed_upload_id`) sees an empty list / 404, never a 500.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.api.deps import CurrentUserDep, SessionDep
from src.api.schemas import ClientSummary, PositionResponse
from src.db.repositories import analytics as analytics_repo
from src.db.repositories import positions as positions_repo

router = APIRouter()


@router.get("/clients", response_model=list[ClientSummary])
async def list_clients(user: CurrentUserDep, session: SessionDep) -> list[ClientSummary]:
    """One row per distinct client in the user's currently selected upload."""
    if user.last_viewed_upload_id is None:
        return []
    rows = await analytics_repo.get_client_summary(session, user.last_viewed_upload_id)
    return [ClientSummary(**row) for row in rows]


@router.get(
    "/clients/{client_id}/positions",
    response_model=list[PositionResponse],
    responses={404: {"description": "Client not found in active upload"}},
)
async def get_client_positions(
    client_id: str,
    user: CurrentUserDep,
    session: SessionDep,
) -> list[PositionResponse]:
    """All positions for one client, ordered by ISIN."""
    if user.last_viewed_upload_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active upload selected",
        )
    rows = await positions_repo.get_by_upload_and_client(
        session, upload_id=user.last_viewed_upload_id, client_id=client_id
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client {client_id} not found in active upload",
        )
    return [PositionResponse.model_validate(row) for row in rows]
