"""
Uploads repository — shared upload pool (ADR 016).

All uploads are visible to every user in the organization. There is no
per-user ownership concept, so this module has no ownership checks and no
advisory-lock helpers; per-user state (which upload was last viewed) lives
on the `users` table and is managed by `repositories.users.update_last_viewed`.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Upload


async def insert(
    session: AsyncSession,
    *,
    filename: str,
    file_content: bytes,
    row_count: int,
    violation_count: int,
) -> Upload:
    """Insert a new upload row and return it with `id` populated."""
    upload = Upload(
        filename=filename,
        file_content=file_content,
        row_count=row_count,
        violation_count=violation_count,
    )
    session.add(upload)
    await session.flush()
    return upload


async def get_all(session: AsyncSession) -> Sequence[Upload]:
    """Return every upload in the system, newest first."""
    stmt = select(Upload).order_by(Upload.uploaded_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_by_id(session: AsyncSession, upload_id: int) -> Upload | None:
    """Return the upload with this id, or None."""
    return await session.get(Upload, upload_id)
