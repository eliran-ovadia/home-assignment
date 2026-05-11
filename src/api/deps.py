"""
FastAPI dependencies — the single resolution point for "who is the user"
and "where is the DB session".

`get_current_user` is the *only* place that interprets `X-Session-Token`.
Every route receives a typed `User` row via `Depends(get_current_user)`;
no route reads the raw header. This is what makes the OIDC swap-in
described in ADR 016 a one-function change.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_session
from src.db.models import User
from src.db.repositories import users as users_repo

# `get_session` is re-exported from `src.core.database` directly (no api-layer
# wrapper) — the wrapper would be pure indirection. Tests that need a custom
# session factory override `src.core.database.get_session` via
# `app.dependency_overrides`.

_EMAIL_VALIDATOR: TypeAdapter[EmailStr] = TypeAdapter(EmailStr)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep,
    x_session_token: Annotated[str | None, Header(alias="X-Session-Token")] = None,
) -> User:
    """
    Resolve `X-Session-Token` (a corporate email, per ADR 016) into a `User` row.

    Creates the row on first sight via `users.get_or_create_by_email`. Raises
    `400 Bad Request` if the header is missing or not a valid email address —
    the API never silently accepts unidentified callers.
    """
    if not x_session_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Session-Token header (expected corporate email)",
        )
    try:
        email = _EMAIL_VALIDATOR.validate_python(x_session_token.strip())
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Session-Token must be a valid corporate email address",
        ) from exc
    return await users_repo.get_or_create_by_email(session, email)


CurrentUserDep = Annotated[User, Depends(get_current_user)]
