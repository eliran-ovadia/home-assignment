"""
Users repository — corporate-email identity (ADR 016).

The application is deployed inside a single organization's intranet; the
trust boundary is the network perimeter plus the verified corporate email
chain. The frontend captures the user's email once (per device) and submits
it on every request. Email validation (`pydantic.EmailStr`) happens at the
API boundary; this layer treats the value as an opaque `str` so it can be
swapped for an IdP-injected claim without touching the repository code.
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User


async def get_or_create_by_email(session: AsyncSession, email: str) -> User:
    """
    Return the `User` for *email*, creating one on first sight.

    Uses Postgres `INSERT ... ON CONFLICT (email) DO NOTHING RETURNING` so
    two concurrent requests from the same brand-new email can't both pass a
    `SELECT … is None` check and then race on the insert. On conflict the
    insert is a no-op and we fall back to a follow-up `SELECT`.

    Isolation assumption: the fallback `SELECT` is safe under `READ COMMITTED`
    (the asyncpg / PostgreSQL default), because by the time the conflicting
    INSERT returns we know the winning row was already committed and is
    visible to subsequent statements. Under `REPEATABLE READ` or
    `SERIALIZABLE` the snapshot taken at the first statement may predate
    that commit and `scalar_one()` could raise `NoResultFound`. If the
    session's isolation level is ever raised, this function needs to
    re-issue the SELECT in a fresh sub-transaction or sleep-retry.

    The caller is responsible for validating the email format
    (`pydantic.EmailStr` at the API boundary). This function does not
    re-validate — it accepts whatever string was already trusted at the edge.

    The row is flushed but not committed — the caller owns the transaction.
    """
    insert_stmt = (
        pg_insert(User)
        .values(email=email)
        .on_conflict_do_nothing(index_elements=["email"])
        .returning(User)
    )
    result = await session.execute(insert_stmt)
    user = result.scalar_one_or_none()
    if user is not None:
        await session.flush()
        return user

    select_stmt = select(User).where(User.email == email)
    return (await session.execute(select_stmt)).scalar_one()


async def update_last_viewed(session: AsyncSession, *, user_id: int, upload_id: int | None) -> None:
    """
    Set the user's `last_viewed_upload_id` preference.

    Pass `upload_id=None` to clear the preference. The FK constraint on
    `users.last_viewed_upload_id` will reject an *upload_id* that doesn't
    exist; the caller may rely on that to validate the input.
    """
    await session.execute(
        update(User).where(User.id == user_id).values(last_viewed_upload_id=upload_id)
    )
