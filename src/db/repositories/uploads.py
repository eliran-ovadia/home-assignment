"""Uploads repository — file history per user (ADR 014)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Upload


async def insert(
    session: AsyncSession,
    *,
    user_id: int,
    filename: str,
    file_content: bytes,
    row_count: int,
    violation_count: int,
    is_active: bool = True,
) -> Upload:
    """Insert a new upload row and return it with `id` populated."""
    upload = Upload(
        user_id=user_id,
        filename=filename,
        file_content=file_content,
        row_count=row_count,
        violation_count=violation_count,
        is_active=is_active,
    )
    session.add(upload)
    await session.flush()
    return upload


async def get_all_by_user(session: AsyncSession, user_id: int) -> Sequence[Upload]:
    """Return all uploads for one user, newest first."""
    stmt = select(Upload).where(Upload.user_id == user_id).order_by(Upload.uploaded_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_by_id(session: AsyncSession, upload_id: int) -> Upload | None:
    """Return the upload with this id, or None."""
    return await session.get(Upload, upload_id)


async def get_active_for_user(session: AsyncSession, user_id: int) -> Upload | None:
    """Return the user's currently-active upload, or None if they have none."""
    stmt = select(Upload).where(Upload.user_id == user_id, Upload.is_active.is_(True))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def set_active(session: AsyncSession, *, user_id: int, upload_id: int) -> None:
    """
    Switch the user's active upload to *upload_id*.

    Deactivates every other upload for the user in the same statement, so the
    "at most one active upload per user" invariant holds atomically.
    """
    await session.execute(
        update(Upload)
        .where(Upload.user_id == user_id, Upload.id != upload_id)
        .values(is_active=False)
    )
    await session.execute(update(Upload).where(Upload.id == upload_id).values(is_active=True))
