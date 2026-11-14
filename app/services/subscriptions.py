from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import Settings, get_settings
from app.core.plans import PLANS, Plan, get_plan
from app.core.security import generate_activation_token, hash_token
from app.core.timeutil import add_calendar_months, ensure_utc, utcnow
from app.models.entities import (
    ActivationToken,
    Grant,
    GrantSource,
    Order,
    OrderStatus,
    Payment,
    PaymentProvider,
    PaymentStatus,
    User,
)
from app.services.jobs import cancel_jobs_by_prefix, enqueue_job
from app.services.users import get_or_create_user, is_subscription_active


def new_order_public_id() -> str:
    return secrets.token_hex(12)


async def create_order(
    session: AsyncSession,
    *,
    plan_code: str,
    provider: PaymentProvider,
    telegram_user_id: int | None = None,
    deferred_activation: bool = False,
    stars_amount: int | None = None,
) -> Order:
    plan = get_plan(plan_code)
    user = None
    if telegram_user_id is not None:
        user = await get_or_create_user(session, telegram_user_id)
    order = Order(
        public_id=new_order_public_id(),
        user_id=user.id if user else None,
        telegram_user_id=telegram_user_id,
        plan_code=plan.code,
        months=plan.months,
        amount_kopecks=plan.amount_kopecks,
        currency="XTR" if provider == PaymentProvider.stars else "RUB",
        stars_amount=stars_amount,
        status=OrderStatus.pending,
        provider=provider,
        deferred_activation=deferred_activation or telegram_user_id is None,
    )
    session.add(order)
    await session.flush()
    return order


async def create_activation_token(
    session: AsyncSession,
    order: Order,
    *,
    settings: Settings | None = None,
    ttl_hours: int = 72,
) -> str:
    settings = settings or get_settings()
    existing = await session.execute(
        select(ActivationToken).where(ActivationToken.order_id == order.id)
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("Activation token already issued for this order")
    raw = generate_activation_token()
    token = ActivationToken(
        order_id=order.id,
        token_hash=hash_token(raw, pepper=settings.secret_key),
        expires_at=ensure_utc(utcnow() + timedelta(hours=ttl_hours)),
    )
    session.add(token)
    await session.flush()
    return raw


async def apply_grant(
    session: AsyncSession,
    user: User,
    *,
    months: int,
    source: GrantSource,
    order: Order | None = None,
    payment: Payment | None = None,
    reason: str | None = None,
    admin_id: int | None = None,
    now: datetime | None = None,
) -> Grant:
    now = ensure_utc(now or utcnow())
    base = now
    if user.subscription_ends_at and ensure_utc(user.subscription_ends_at) > now:
        base = ensure_utc(user.subscription_ends_at)
    ends = add_calendar_months(base, months)
    grant = Grant(
        user_id=user.id,
        order_id=order.id if order else None,
        payment_id=payment.id if payment else None,
        source=source,
        months=months,
        starts_at=base,
        ends_at=ends,
        delta_days=(ends - base).days,
        reason=reason,
        admin_id=admin_id,
    )
    session.add(grant)
    old_ends = user.subscription_ends_at
    user.subscription_ends_at = ensure_utc(ends)
    await session.flush()

    # Cancel old reminder jobs keyed by previous ends_at
    if old_ends is not None:
        await cancel_jobs_by_prefix(session, f"reminder:{user.id}:{old_ends.isoformat()}")
    await schedule_reminders(session, user)
    await enqueue_job(
        session,
        "provision_access",
        {"telegram_user_id": user.telegram_user_id, "user_id": user.id},
        unique_key=f"provision:{user.id}:{ends.isoformat()}",
    )
    await enqueue_job(
        session,
        "notify_access_granted",
        {"telegram_user_id": user.telegram_user_id, "ends_at": ends.isoformat()},
        unique_key=f"notify-grant:{user.id}:{ends.isoformat()}",
    )
    return grant


async def schedule_reminders(session: AsyncSession, user: User) -> None:
    if user.subscription_ends_at is None:
        return
    ends = ensure_utc(user.subscription_ends_at)
    version = ends.isoformat()
    for reminder_type, delta in (("d3", timedelta(days=3)), ("d1", timedelta(days=1))):
        run_at = ends - delta
        if run_at > utcnow():
            await enqueue_job(
                session,
                "send_reminder",
                {
                    "user_id": user.id,
                    "telegram_user_id": user.telegram_user_id,
                    "reminder_type": reminder_type,
                    "ends_at": version,
                },
                unique_key=f"reminder:{user.id}:{version}:{reminder_type}",
                run_at=run_at,
            )
    await enqueue_job(
        session,
        "send_reminder",
        {
            "user_id": user.id,
            "telegram_user_id": user.telegram_user_id,
            "reminder_type": "expired",
            "ends_at": version,
        },
        unique_key=f"reminder:{user.id}:{version}:expired",
        run_at=ends,
    )


async def mark_payment_succeeded(
    session: AsyncSession,
    payment: Payment,
    *,
    amount_kopecks: int | None = None,
    currency: str | None = None,
    stars_amount: int | None = None,
    raw_payload: dict | None = None,
    telegram_charge_id: str | None = None,
    now: datetime | None = None,
) -> tuple[Order, Grant | None]:
    """Idempotent confirmation of a payment. Returns grant if newly applied."""
    now = ensure_utc(now or utcnow())
    order = await session.get(Order, payment.order_id)
    if order is None:
        raise ValueError("Order missing for payment")

    if payment.status == PaymentStatus.succeeded:
        # Already processed — do not double-credit
        return order, None

    if amount_kopecks is not None and amount_kopecks != order.amount_kopecks:
        if order.provider == PaymentProvider.yookassa:
            raise ValueError("Payment amount mismatch")
    if currency is not None and currency.upper() != order.currency.upper():
        if order.provider == PaymentProvider.yookassa:
            raise ValueError("Payment currency mismatch")

    payment.status = PaymentStatus.succeeded
    payment.succeeded_at = now
    if amount_kopecks is not None:
        payment.amount_kopecks = amount_kopecks
    if currency is not None:
        payment.currency = currency
    if stars_amount is not None:
        payment.stars_amount = stars_amount
    if telegram_charge_id is not None:
        payment.telegram_charge_id = telegram_charge_id
    if raw_payload is not None:
        payment.raw_payload = raw_payload

    grant: Grant | None = None
    if order.deferred_activation or order.telegram_user_id is None:
        order.status = OrderStatus.paid_unactivated
        token_row = await session.execute(
            select(ActivationToken).where(ActivationToken.order_id == order.id)
        )
        if token_row.scalar_one_or_none() is None:
            await enqueue_job(
                session,
                "notify_paid_unactivated",
                {"order_id": order.id},
                unique_key=f"paid-unactivated:{order.id}",
            )
    else:
        user = await get_or_create_user(session, order.telegram_user_id)
        order.user_id = user.id
        order.status = OrderStatus.paid
        order.activated_at = now
        order.activated_by_telegram_id = user.telegram_user_id
        grant = await apply_grant(
            session,
            user,
            months=order.months,
            source=GrantSource.payment,
            order=order,
            payment=payment,
            now=now,
        )

    await session.flush()
    return order, grant


async def activate_order_with_token(
    session: AsyncSession,
    *,
    raw_token: str,
    telegram_user_id: int,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> tuple[Order, Grant]:
    settings = settings or get_settings()
    now = ensure_utc(now or utcnow())
    token_hash = hash_token(raw_token, pepper=settings.secret_key)
    result = await session.execute(
        select(ActivationToken).where(ActivationToken.token_hash == token_hash)
    )
    token = result.scalar_one_or_none()
    if token is None:
        raise ValueError("Неверный токен активации")
    if token.used_at is not None:
        if token.used_by_telegram_id == telegram_user_id:
            raise ValueError("Этот заказ уже активирован на ваш аккаунт")
        raise ValueError("Токен уже использован другим аккаунтом")
    if ensure_utc(token.expires_at) < now:
        raise ValueError("Срок действия токена истёк")

    order = await session.get(Order, token.order_id)
    if order is None:
        raise ValueError("Заказ не найден")
    if order.status not in {OrderStatus.paid_unactivated, OrderStatus.paid}:
        raise ValueError("Заказ ещё не оплачен")
    if order.activated_at is not None:
        raise ValueError("Заказ уже активирован")

    user = await get_or_create_user(session, telegram_user_id, mark_started=True)
    token.used_at = now
    token.used_by_telegram_id = telegram_user_id
    order.user_id = user.id
    order.telegram_user_id = telegram_user_id
    order.status = OrderStatus.paid
    order.activated_at = now
    order.activated_by_telegram_id = telegram_user_id

    payment_result = await session.execute(
        select(Payment).where(
            Payment.order_id == order.id, Payment.status == PaymentStatus.succeeded
        )
    )
    payment = payment_result.scalar_one_or_none()
    grant = await apply_grant(
        session,
        user,
        months=order.months,
        source=GrantSource.activation,
        order=order,
        payment=payment,
        now=now,
    )
    return order, grant


async def activate_order_for_user(
    session: AsyncSession,
    order: Order,
    telegram_user_id: int,
    *,
    now: datetime | None = None,
) -> Grant:
    """Bind a paid_unactivated order via verified Telegram Login."""
    now = ensure_utc(now or utcnow())
    if order.status != OrderStatus.paid_unactivated:
        raise ValueError("Order is not awaiting activation")
    if order.activated_at is not None:
        raise ValueError("Order already activated")
    user = await get_or_create_user(session, telegram_user_id, mark_started=True)
    order.user_id = user.id
    order.telegram_user_id = telegram_user_id
    order.status = OrderStatus.paid
    order.activated_at = now
    order.activated_by_telegram_id = telegram_user_id
    payment_result = await session.execute(
        select(Payment).where(
            Payment.order_id == order.id, Payment.status == PaymentStatus.succeeded
        )
    )
    payment = payment_result.scalar_one_or_none()
    return await apply_grant(
        session,
        user,
        months=order.months,
        source=GrantSource.activation,
        order=order,
        payment=payment,
        now=now,
    )


async def reverse_grant_for_refund(
    session: AsyncSession,
    payment: Payment,
    *,
    full: bool,
    refunded_amount_kopecks: int,
    now: datetime | None = None,
) -> None:
    now = ensure_utc(now or utcnow())
    order = await session.get(Order, payment.order_id)
    if order is None:
        return
    if not full:
        order.status = OrderStatus.partially_refunded
        payment.status = PaymentStatus.partially_refunded
        payment.refunded_amount_kopecks = refunded_amount_kopecks
        await enqueue_job(
            session,
            "admin_alert",
            {
                "text": (
                    f"Частичный возврат по заказу {order.public_id}: "
                    f"{refunded_amount_kopecks}коп. Требуется ручная проверка."
                )
            },
            unique_key=f"partial-refund:{payment.id}:{refunded_amount_kopecks}",
        )
        await session.flush()
        return

    payment.status = PaymentStatus.refunded
    payment.refunded_amount_kopecks = refunded_amount_kopecks or payment.amount_kopecks or 0
    order.status = OrderStatus.refunded

    result = await session.execute(
        select(Grant).where(
            Grant.order_id == order.id,
            Grant.reversed.is_(False),
            Grant.source.in_([GrantSource.payment, GrantSource.activation]),
        )
    )
    grants = list(result.scalars().all())
    for grant in grants:
        grant.reversed = True
        if order.user_id:
            user = await session.get(User, order.user_id)
            if user and user.subscription_ends_at:
                # Recalculate ends_at from remaining non-reversed grants
                await recalculate_subscription_end(session, user, now=now)
    await session.flush()


async def recalculate_subscription_end(
    session: AsyncSession, user: User, *, now: datetime | None = None
) -> None:
    now = ensure_utc(now or utcnow())
    result = await session.execute(
        select(Grant).where(Grant.user_id == user.id).order_by(Grant.created_at, Grant.id)
    )
    all_grants = list(result.scalars().all())
    active = [g for g in all_grants if not g.reversed]
    if not active:
        user.subscription_ends_at = None
        await enqueue_job(
            session,
            "expire_access",
            {"user_id": user.id, "telegram_user_id": user.telegram_user_id},
            unique_key=f"expire-recalc:{user.id}:{now.isoformat()}",
        )
        await session.flush()
        return

    # Stack remaining months from the original subscription origin so a refund
    # removes only its own accrual and does not leave a phantom gap.
    origin = ensure_utc(all_grants[0].starts_at)
    cursor = origin
    for grant in active:
        cursor = add_calendar_months(cursor, grant.months)
    user.subscription_ends_at = cursor
    await cancel_jobs_by_prefix(session, f"reminder:{user.id}:")
    await schedule_reminders(session, user)
    if cursor > now:
        await enqueue_job(
            session,
            "provision_access",
            {"telegram_user_id": user.telegram_user_id, "user_id": user.id},
            unique_key=f"provision-recalc:{user.id}:{cursor.isoformat()}",
        )
    else:
        await enqueue_job(
            session,
            "expire_access",
            {"user_id": user.id, "telegram_user_id": user.telegram_user_id},
            unique_key=f"expire-recalc:{user.id}:{now.isoformat()}",
        )
    await session.flush()


async def manual_grant(
    session: AsyncSession,
    user: User,
    *,
    months: int,
    admin_id: int,
    reason: str,
    now: datetime | None = None,
) -> Grant:
    return await apply_grant(
        session,
        user,
        months=months,
        source=GrantSource.manual,
        reason=reason,
        admin_id=admin_id,
        now=now,
    )


async def manual_revoke(
    session: AsyncSession,
    user: User,
    *,
    admin_id: int,
    reason: str,
    now: datetime | None = None,
) -> None:
    now = ensure_utc(now or utcnow())
    user.subscription_ends_at = now
    await cancel_jobs_by_prefix(session, f"reminder:{user.id}:")
    await enqueue_job(
        session,
        "expire_access",
        {
            "user_id": user.id,
            "telegram_user_id": user.telegram_user_id,
            "reason": reason,
            "admin_id": admin_id,
        },
        unique_key=f"manual-revoke:{user.id}:{now.isoformat()}",
    )
    from app.models.entities import AdminAction

    session.add(
        AdminAction(
            admin_id=admin_id,
            action="revoke",
            target_user_id=user.telegram_user_id,
            detail=reason,
        )
    )
    await session.flush()


def list_plans_for_display(settings: Settings | None = None) -> list[Plan]:
    return list(PLANS.values())


def subscription_status_text(user: User, settings: Settings | None = None) -> str:
    from app.core.timeutil import format_novosibirsk, remaining_human

    settings = settings or get_settings()
    auto = "включено" if getattr(user, "auto_renew_enabled", False) else "выключено"
    auto_note = (
        "Автопродление (рекуррент): ваше предпочтение сохранено.\n"
        "Когда рекуррентные платежи будут подключены, при включённом "
        "автопродлении подписка будет продлеваться автоматически."
    )
    if is_subscription_active(user):
        ends = user.subscription_ends_at
        assert ends is not None
        return (
            "Моя подписка\n\n"
            "Статус: активна\n"
            f"Срок до: {format_novosibirsk(ends, settings.display_timezone)}\n"
            f"Осталось: {remaining_human(ends)}\n"
            f"Автопродление: {auto}\n\n"
            f"{auto_note}"
        )
    if user.subscription_ends_at:
        return (
            "Моя подписка\n\n"
            "Статус: истекла\n"
            f"Срок закончился: {format_novosibirsk(user.subscription_ends_at, settings.display_timezone)}\n"
            f"Осталось: —\n"
            f"Автопродление: {auto}\n\n"
            "Оформите новую подписку, чтобы снова открыть доступ.\n\n"
            f"{auto_note}"
        )
    return (
        "Моя подписка\n\n"
        "Статус: нет активной подписки\n"
        "Срок до: —\n"
        "Осталось: —\n"
        f"Автопродление: {auto}\n\n"
        "Оформите подписку, чтобы открыть канал и комментарии.\n\n"
        f"{auto_note}"
    )


async def set_auto_renew(session: AsyncSession, user: User, *, enabled: bool) -> User:
    """Persist auto-renew preference and append a tracking event."""
    from app.models.entities import AutoRenewEvent

    user.auto_renew_enabled = enabled
    session.add(AutoRenewEvent(user_id=user.id, enabled=enabled))
    await session.flush()
    return user
