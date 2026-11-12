from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utcnow
from app.models.entities import (
    Broadcast,
    BroadcastDelivery,
    BroadcastStatus,
    User,
)
from app.services.users import is_subscription_active


SEGMENT_ALL = "all"
SEGMENT_ACTIVE = "active"
SEGMENT_EXPIRED = "expired"
SEGMENT_NEVER = "never_bought"


async def create_broadcast(
    session: AsyncSession,
    *,
    admin_id: int,
    text: str,
    segment: str = SEGMENT_ALL,
    media_type: str | None = None,
    media_file_id: str | None = None,
    buttons: list[dict] | None = None,
) -> Broadcast:
    bc = Broadcast(
        created_by_admin_id=admin_id,
        segment=segment,
        text=text,
        media_type=media_type,
        media_file_id=media_file_id,
        buttons_json=buttons,
        status=BroadcastStatus.draft,
    )
    session.add(bc)
    await session.flush()
    return bc


async def count_segment(session: AsyncSession, segment: str) -> int:
    q = select(func.count()).select_from(User).where(
        User.started_at.is_not(None),
        User.blocked_bot.is_(False),
        User.broadcasts_opt_out.is_(False),
    )
    result = await session.execute(select(User).where(
        User.started_at.is_not(None),
        User.blocked_bot.is_(False),
        User.broadcasts_opt_out.is_(False),
    ))
    users = list(result.scalars().all())
    now = utcnow()
    count = 0
    for user in users:
        if segment == SEGMENT_ALL:
            count += 1
        elif segment == SEGMENT_ACTIVE and is_subscription_active(user, now):
            count += 1
        elif segment == SEGMENT_EXPIRED:
            if user.subscription_ends_at and not is_subscription_active(user, now):
                count += 1
        elif segment == SEGMENT_NEVER:
            if user.subscription_ends_at is None:
                # rough: never had ends_at — also check grants externally if needed
                count += 1
    return count


async def confirm_broadcast(session: AsyncSession, broadcast_id: int) -> Broadcast:
    bc = await session.get(Broadcast, broadcast_id)
    if bc is None:
        raise ValueError("Broadcast not found")
    bc.total_targets = await count_segment(session, bc.segment)
    bc.status = BroadcastStatus.confirmed
    await session.flush()
    return bc


async def start_broadcast(session: AsyncSession, broadcast_id: int) -> Broadcast:
    bc = await confirm_broadcast(session, broadcast_id)
    bc.status = BroadcastStatus.sending
    await session.flush()
    from app.services.jobs import enqueue_job

    await enqueue_job(
        session,
        "broadcast_tick",
        {"broadcast_id": bc.id},
        unique_key=f"broadcast-tick:{bc.id}:0",
    )
    return bc


async def next_broadcast_targets(
    session: AsyncSession, bc: Broadcast, *, limit: int = 25
) -> list[User]:
    result = await session.execute(
        select(User)
        .where(
            User.id > bc.cursor_user_id,
            User.started_at.is_not(None),
            User.blocked_bot.is_(False),
            User.broadcasts_opt_out.is_(False),
        )
        .order_by(User.id)
        .limit(limit * 3)
    )
    candidates = list(result.scalars().all())
    now = utcnow()
    selected: list[User] = []
    for user in candidates:
        if bc.segment == SEGMENT_ACTIVE and not is_subscription_active(user, now):
            continue
        if bc.segment == SEGMENT_EXPIRED and not (
            user.subscription_ends_at and not is_subscription_active(user, now)
        ):
            continue
        if bc.segment == SEGMENT_NEVER and user.subscription_ends_at is not None:
            continue
        # skip already delivered
        existing = await session.execute(
            select(BroadcastDelivery).where(
                BroadcastDelivery.broadcast_id == bc.id,
                BroadcastDelivery.user_id == user.id,
            )
        )
        if existing.scalar_one_or_none():
            continue
        selected.append(user)
        if len(selected) >= limit:
            break
    return selected


async def mark_delivery(
    session: AsyncSession,
    bc: Broadcast,
    user: User,
    *,
    ok: bool,
    error: str | None = None,
) -> None:
    delivery = BroadcastDelivery(
        broadcast_id=bc.id,
        user_id=user.id,
        status="sent" if ok else "failed",
        error=error,
        sent_at=utcnow() if ok else None,
    )
    session.add(delivery)
    if ok:
        bc.sent_count += 1
    else:
        bc.failed_count += 1
        if error and "blocked" in error.lower():
            user.blocked_bot = True
    bc.cursor_user_id = max(bc.cursor_user_id, user.id)
    await session.flush()


async def finish_if_done(session: AsyncSession, bc: Broadcast) -> bool:
    more = await next_broadcast_targets(session, bc, limit=1)
    if not more:
        bc.status = BroadcastStatus.done
        bc.finished_at = utcnow()
        await session.flush()
        return True
    return False
