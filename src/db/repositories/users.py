"""Users repository — anonymous-session row lookup (ADR 015)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User


async def get_or_create_by_token(session: AsyncSession, token: uuid.UUID) -> User:
    """
    Return the `User` for *token*, creating one on first sight.

    The row is flushed (to populate `user.id`) but not committed — the caller
    decides the transaction boundary.
    """
    result = await session.execute(select(User).where(User.session_token == token))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = User(session_token=token)
    session.add(user)
    await session.flush()
    return user
