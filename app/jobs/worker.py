from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as dbmod
from app.core.config import Settings, get_settings
from app.core.timeutil import ensure_utc, format_novosibirsk, utcnow
from app.models.entities import Broadcast, BroadcastStatus, ReminderSent, ReminderType, User
from app.services.access import (
    TelegramAccessClient,
    expire_access,
    provision_access,
    sweep_expired,
)
from app.services.broadcasts import finish_if_done, mark_delivery, next_broadcast_targets
from app.services.jobs import (
    claim_jobs,
    complete_job,
    enqueue_job,
    fail_job,
    new_worker_id,
)

logger = logging.getLogger(__name__)


class BotNotifier(Protocol):
    async def send_message(
        self, telegram_user_id: int, text: str, reply_markup: Any | None = None
    ) -> None: ...

    async def send_broadcast_item(
        self, telegram_user_id: int, broadcast: Broadcast
    ) -> None: ...

    async def notify_admins(self, text: str) -> None: ...


class NullNotifier:
    def __init__(self) -> None:
        self.messages: list[tuple] = []
        self.admin_messages: list[str] = []

    async def send_message(
        self, telegram_user_id: int, text: str, reply_markup: Any | None = None
    ) -> None:
        self.messages.append((telegram_user_id, text, reply_markup))

    async def send_broadcast_item(
        self, telegram_user_id: int, broadcast: Broadcast
    ) -> None:
        self.messages.append((telegram_user_id, broadcast.text, None))

    async def notify_admins(self, text: str) -> None:
        self.admin_messages.append(text)


async def process_job(
    session: AsyncSession,
    job,
    *,
    access_client: TelegramAccessClient,
    notifier: BotNotifier,
    settings: Settings,
) -> None:
    payload = job.payload or {}
    jtype = job.job_type

    if jtype == "provision_access":
        await provision_access(
            session, access_client, payload["telegram_user_id"], settings=settings
        )
    elif jtype == "expire_access":
        await expire_access(
            session,
            access_client,
            payload["telegram_user_id"],
            expected_ends_at=payload.get("ends_at"),
            settings=settings,
        )
    elif jtype == "notify_access_granted":
        tid = payload["telegram_user_id"]
        ends = payload.get("ends_at")
        ends_txt = "—"
        if ends:
            ends_txt = format_novosibirsk(
                ensure_utc(datetime.fromisoformat(ends)), settings.display_timezone
            )
        text = (
            "Оплата подтверждена. Подписка активна.\n"
            f"Действует до: {ends_txt}\n\n"
            "Доступ к закрытому каналу и комментариям."
        )
        await notifier.send_message(tid, text)
    elif jtype == "send_reminder":
        await _send_reminder(session, notifier, payload, settings)
    elif jtype == "broadcast_tick":
        await _broadcast_tick(session, notifier, payload, settings)
    elif jtype == "admin_alert":
        await notifier.notify_admins(payload.get("text", "alert"))
    elif jtype == "deliver_activation_token":
        await notifier.notify_admins(
            f"Заказ #{payload.get('order_id')} оплачен (ожидает активации). "
            "Токен выдан на веб-странице."
        )
    elif jtype == "notify_paid_unactivated":
        await notifier.notify_admins(
            f"Заказ {payload.get('order_id')} оплачен и ждёт привязки Telegram."
        )
    elif jtype == "expire_sweep":
        await sweep_expired(session, access_client, settings=settings)
    else:
        raise ValueError(f"Unknown job type: {jtype}")


async def _send_reminder(
    session: AsyncSession, notifier: BotNotifier, payload: dict, settings: Settings
) -> None:
    user = await session.get(User, payload["user_id"])
    if user is None or user.subscription_ends_at is None:
        return
    ends_version = payload["ends_at"]
    if ensure_utc(user.subscription_ends_at).isoformat() != ends_version:
        return
    rtype = ReminderType(payload["reminder_type"])
    existing = await session.execute(
        select(ReminderSent).where(
            ReminderSent.user_id == user.id,
            ReminderSent.ends_at_version == user.subscription_ends_at,
            ReminderSent.reminder_type == rtype,
        )
    )
    if existing.scalar_one_or_none():
        return
    session.add(
        ReminderSent(
            user_id=user.id,
            ends_at_version=user.subscription_ends_at,
            reminder_type=rtype,
        )
    )
    ends_txt = format_novosibirsk(user.subscription_ends_at, settings.display_timezone)
    if rtype == ReminderType.d3:
        text = (
            f"Напоминание: подписка закончится через 3 дня ({ends_txt}). "
            "Разовая оплата. Без автоматических списаний."
        )
    elif rtype == ReminderType.d1:
        text = f"Напоминание: подписка закончится завтра ({ends_txt})."
    else:
        text = f"Подписка закончилась ({ends_txt}). Продлите, чтобы снова войти в канал."
    try:
        await notifier.send_message(user.telegram_user_id, text)
    except Exception as exc:  # noqa: BLE001
        if "blocked" in str(exc).lower():
            user.blocked_bot = True
        raise
    await session.flush()


async def _broadcast_tick(
    session: AsyncSession, notifier: BotNotifier, payload: dict, settings: Settings
) -> None:
    bc = await session.get(Broadcast, payload["broadcast_id"])
    if bc is None or bc.status in {BroadcastStatus.canceled, BroadcastStatus.done}:
        return
    if bc.status == BroadcastStatus.paused:
        return
    bc.status = BroadcastStatus.sending
    targets = await next_broadcast_targets(
        session, bc, limit=max(1, int(settings.broadcast_rate_limit_per_sec))
    )
    if not targets:
        await finish_if_done(session, bc)
        return
    for user in targets:
        try:
            await notifier.send_broadcast_item(user.telegram_user_id, bc)
            await mark_delivery(session, bc, user, ok=True)
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            await mark_delivery(session, bc, user, ok=False, error=err)
            if "retry_after" in err.lower():
                bc.status = BroadcastStatus.paused
                await enqueue_job(
                    session,
                    "broadcast_tick",
                    {"broadcast_id": bc.id},
                    unique_key=f"broadcast-tick:{bc.id}:{bc.cursor_user_id}:retry",
                    run_at=utcnow() + timedelta(seconds=30),
                )
                await session.flush()
                return
    done = await finish_if_done(session, bc)
    if not done:
        await enqueue_job(
            session,
            "broadcast_tick",
            {"broadcast_id": bc.id},
            unique_key=f"broadcast-tick:{bc.id}:{bc.cursor_user_id}",
            run_at=utcnow() + timedelta(seconds=1),
        )


async def run_once(
    *,
    access_client: TelegramAccessClient,
    notifier: BotNotifier,
    settings: Settings | None = None,
    worker_id: str | None = None,
) -> int:
    settings = settings or get_settings()
    worker_id = worker_id or new_worker_id()
    async with dbmod.SessionLocal() as session:
        jobs = await claim_jobs(session, worker_id=worker_id, limit=10)
        await session.commit()
        job_ids = [j.id for j in jobs]

    processed = 0
    for job_id in job_ids:
        async with dbmod.SessionLocal() as session:
            from app.models.entities import Job

            fresh = await session.get(Job, job_id)
            if fresh is None:
                continue
            try:
                await process_job(
                    session,
                    fresh,
                    access_client=access_client,
                    notifier=notifier,
                    settings=settings,
                )
                await complete_job(session, fresh)
                await session.commit()
                processed += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("job failed: %s", fresh.job_type)
                await fail_job(session, fresh, str(exc))
                await session.commit()
    return processed


async def worker_loop(
    *,
    access_client: TelegramAccessClient,
    notifier: BotNotifier,
    settings: Settings | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    settings = settings or get_settings()
    stop_event = stop_event or asyncio.Event()
    worker_id = new_worker_id()
    last_sweep = 0.0
    while not stop_event.is_set():
        await run_once(
            access_client=access_client,
            notifier=notifier,
            settings=settings,
            worker_id=worker_id,
        )
        now = asyncio.get_running_loop().time()
        if now - last_sweep >= settings.expire_sweep_interval_sec:
            async with dbmod.SessionLocal() as session:
                await enqueue_job(
                    session,
                    "expire_sweep",
                    {},
                    unique_key=f"expire-sweep:{int(now)}",
                )
                await session.commit()
            last_sweep = now
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.job_poll_interval_sec)
        except TimeoutError:
            pass
