from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin_web
from app.core.db import get_session
from app.core.timeutil import utcnow
from app.models.entities import Job, JobStatus, Payment, PaymentStatus, User

router = APIRouter(prefix="/admin/api", tags=["admin"], dependencies=[Depends(require_admin_web)])


@router.get("/stats")
async def stats(session: AsyncSession = Depends(get_session)) -> dict:
    users = await session.scalar(select(func.count()).select_from(User)) or 0
    active = await session.scalar(
        select(func.count()).select_from(User).where(User.subscription_ends_at > utcnow())
    ) or 0
    confirmed = await session.scalar(
        select(func.count()).select_from(Payment).where(Payment.status == PaymentStatus.succeeded)
    ) or 0
    refunds = await session.scalar(
        select(func.count())
        .select_from(Payment)
        .where(Payment.status.in_([PaymentStatus.refunded, PaymentStatus.partially_refunded]))
    ) or 0
    failed_jobs = await session.scalar(
        select(func.count()).select_from(Job).where(Job.status == JobStatus.failed)
    ) or 0
    return {
        "users": users,
        "active_subscriptions": active,
        "confirmed_payments": confirmed,
        "refunds": refunds,
        "failed_jobs": failed_jobs,
    }


@router.get("/users/{telegram_user_id}")
async def user_card(
    telegram_user_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    result = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return {"found": False}
    return {
        "found": True,
        "telegram_user_id": user.telegram_user_id,
        "username": user.username,
        "subscription_ends_at": user.subscription_ends_at.isoformat()
        if user.subscription_ends_at
        else None,
        "channel_access_state": user.channel_access_state,
        "discussion_access_state": user.discussion_access_state,
        "blocked_bot": user.blocked_bot,
    }
