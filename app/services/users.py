from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utcnow
from app.models.entities import User


async def get_or_create_user(
    session: AsyncSession,
    telegram_user_id: int,
    *,
    username: str | None = None,
    full_name: str | None = None,
    language_code: str | None = None,
    mark_started: bool = False,
) -> User:
    result = await session.execute(
        select(User).where(User.telegram_user_id == telegram_user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_user_id=telegram_user_id,
            username=username,
            full_name=full_name,
            language_code=language_code,
            started_at=utcnow() if mark_started else None,
        )
        session.add(user)
        await session.flush()
        return user

    if username is not None:
        user.username = username
    if full_name is not None:
        user.full_name = full_name
    if language_code is not None:
        user.language_code = language_code
    if mark_started:
        if user.started_at is None:
            user.started_at = utcnow()
        user.blocked_bot = False
    await session.flush()
    return user


async def get_user_by_telegram_id(
    session: AsyncSession, telegram_user_id: int
) -> User | None:
    result = await session.execute(
        select(User).where(User.telegram_user_id == telegram_user_id)
    )
    return result.scalar_one_or_none()


def is_subscription_active(user: User, now=None) -> bool:
    from app.core.timeutil import ensure_utc, utcnow as _utcnow

    now = ensure_utc(now or _utcnow())
    if user.subscription_ends_at is None:
        return False
    return ensure_utc(user.subscription_ends_at) > now


def ensure_aware_ends(user: User) -> None:
    from app.core.timeutil import ensure_utc

    if user.subscription_ends_at is not None:
        user.subscription_ends_at = ensure_utc(user.subscription_ends_at)
