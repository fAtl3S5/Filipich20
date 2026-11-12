from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import admin_menu_kb
from app.core.config import Settings
from app.core.timeutil import utcnow
from app.models.entities import Job, JobStatus, Order, OrderStatus, Payment, PaymentStatus, User
from app.services.subscriptions import manual_grant, manual_revoke
from app.services.users import get_or_create_user, get_user_by_telegram_id

router = Router(name="admin")


def _is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_ids


@router.message(Command("admin"))
async def cmd_admin(message: Message, settings: Settings) -> None:
    assert message.from_user
    if not _is_admin(message.from_user.id, settings):
        return
    await message.answer("Админ-панель", reply_markup=admin_menu_kb())


@router.callback_query(F.data.startswith("admin:"))
async def cb_admin(query: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    assert query.from_user
    if not _is_admin(query.from_user.id, settings):
        await query.answer("Нет доступа", show_alert=True)
        return
    action = query.data.split(":", 1)[1]  # type: ignore[union-attr]
    if action == "stats":
        users = await session.scalar(select(func.count()).select_from(User))
        active = await session.scalar(
            select(func.count()).select_from(User).where(User.subscription_ends_at > utcnow())
        )
        paid = await session.scalar(
            select(func.count()).select_from(Payment).where(Payment.status == PaymentStatus.succeeded)
        )
        refunds = await session.scalar(
            select(func.count())
            .select_from(Payment)
            .where(Payment.status.in_([PaymentStatus.refunded, PaymentStatus.partially_refunded]))
        )
        unpaid = await session.scalar(
            select(func.count()).select_from(Order).where(Order.status == OrderStatus.pending)
        )
        text = (
            f"Пользователей: {users}\n"
            f"Активных подписок: {active}\n"
            f"Подтверждённых оплат: {paid}\n"
            f"Возвратов: {refunds}\n"
            f"Неоплаченных заказов: {unpaid}"
        )
        await query.message.answer(text)  # type: ignore[union-attr]
    elif action == "expiring":
        from datetime import timedelta

        until = utcnow() + timedelta(days=3)
        result = await session.execute(
            select(User).where(
                User.subscription_ends_at.is_not(None),
                User.subscription_ends_at > utcnow(),
                User.subscription_ends_at <= until,
            )
        )
        users = list(result.scalars().all())
        lines = [f"{u.telegram_user_id} до {u.subscription_ends_at}" for u in users[:30]]
        await query.message.answer("Истекают:\n" + ("\n".join(lines) or "нет"))  # type: ignore[union-attr]
    elif action == "jobs":
        result = await session.execute(
            select(Job).where(Job.status == JobStatus.failed).order_by(Job.id.desc()).limit(20)
        )
        jobs = list(result.scalars().all())
        lines = [f"#{j.id} {j.job_type}: {j.last_error}" for j in jobs]
        await query.message.answer("Ошибки задач:\n" + ("\n".join(lines) or "нет"))  # type: ignore[union-attr]
    elif action == "diag":
        missing = []
        if settings.channel_id is None:
            missing.append("CHANNEL_ID")
        if settings.discussion_group_id is None:
            missing.append("DISCUSSION_GROUP_ID")
        text = (
            f"CHANNEL_ID={settings.channel_id}\n"
            f"DISCUSSION_GROUP_ID={settings.discussion_group_id}\n"
            f"WEB_YK={settings.enable_web_yookassa}\n"
            f"BOT_YK={settings.enable_bot_initiated_yookassa}\n"
            f"STARS={settings.enable_stars} prices={settings.stars_prices}\n"
            f"missing={missing or 'ok'}"
        )
        await query.message.answer(text)  # type: ignore[union-attr]
    await query.answer()


@router.message(Command("grant"))
async def cmd_grant(message: Message, session: AsyncSession, settings: Settings) -> None:
    """ /grant <telegram_id> <months> <reason> """
    assert message.from_user
    if not _is_admin(message.from_user.id, settings):
        return
    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 4:
        await message.answer("Формат: /grant <telegram_id> <months> <reason>")
        return
    tid, months, reason = int(parts[1]), int(parts[2]), parts[3]
    user = await get_or_create_user(session, tid)
    await manual_grant(
        session, user, months=months, admin_id=message.from_user.id, reason=reason
    )
    await message.answer(f"Выдан grant {months} мес. пользователю {tid} (не выручка)")


@router.message(Command("revoke"))
async def cmd_revoke(message: Message, session: AsyncSession, settings: Settings) -> None:
    assert message.from_user
    if not _is_admin(message.from_user.id, settings):
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: /revoke <telegram_id> <reason>")
        return
    tid, reason = int(parts[1]), parts[2]
    user = await get_user_by_telegram_id(session, tid)
    if user is None:
        await message.answer("Пользователь не найден")
        return
    await manual_revoke(session, user, admin_id=message.from_user.id, reason=reason)
    await message.answer(f"Доступ отозван у {tid}")


@router.message(Command("find"))
async def cmd_find(message: Message, session: AsyncSession, settings: Settings) -> None:
    assert message.from_user
    if not _is_admin(message.from_user.id, settings):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Формат: /find <telegram_id|username>")
        return
    q = parts[1].strip().lstrip("@")
    user = None
    if q.isdigit():
        user = await get_user_by_telegram_id(session, int(q))
    else:
        result = await session.execute(select(User).where(User.username == q))
        user = result.scalar_one_or_none()
    if user is None:
        await message.answer("Не найден")
        return
    await message.answer(
        f"id={user.telegram_user_id} @{user.username}\n"
        f"ends_at={user.subscription_ends_at}\n"
        f"channel={user.channel_access_state} discussion={user.discussion_access_state}\n"
        f"blocked={user.blocked_bot} opt_out={user.broadcasts_opt_out}"
    )


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, session: AsyncSession, settings: Settings) -> None:
    """ /broadcast <segment> <text> — create+confirm+start simplified """
    assert message.from_user
    if not _is_admin(message.from_user.id, settings):
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: /broadcast <all|active|expired|never_bought> <text>")
        return
    from app.services.broadcasts import create_broadcast, start_broadcast

    segment, text = parts[1], parts[2]
    bc = await create_broadcast(
        session, admin_id=message.from_user.id, text=text, segment=segment
    )
    await start_broadcast(session, bc.id)
    await message.answer(f"Рассылка #{bc.id} запущена, сегмент={segment}")
