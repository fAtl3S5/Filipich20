from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import Settings, get_settings
from app.core.plans import get_plan
from app.models.entities import (
    Order,
    OrderStatus,
    Payment,
    PaymentProvider,
    PaymentStatus,
)
from app.payments.yookassa import YooKassaClient, parse_amount_to_kopecks
from app.services.subscriptions import (
    create_activation_token,
    create_order,
    mark_payment_succeeded,
    reverse_grant_for_refund,
)


def make_idempotence_key(order_public_id: str) -> str:
    return f"order-{order_public_id}"


async def start_yookassa_checkout(
    session: AsyncSession,
    client: YooKassaClient,
    *,
    plan_code: str,
    telegram_user_id: int | None,
    settings: Settings | None = None,
    deferred: bool | None = None,
) -> tuple[Order, Payment, str]:
    settings = settings or get_settings()
    plan = get_plan(plan_code)
    deferred_activation = deferred if deferred is not None else telegram_user_id is None
    order = await create_order(
        session,
        plan_code=plan.code,
        provider=PaymentProvider.yookassa,
        telegram_user_id=telegram_user_id,
        deferred_activation=deferred_activation,
    )
    idem = make_idempotence_key(order.public_id)
    yk = await client.create_payment(
        amount_kopecks=plan.amount_kopecks,
        currency="RUB",
        description=f"Подписка «Филипп ещё расскажет» — {plan.title}",
        idempotence_key=idem,
        return_url=settings.yookassa_return_url,
        metadata={"order_public_id": order.public_id},
    )
    payment = Payment(
        order_id=order.id,
        provider=PaymentProvider.yookassa,
        provider_payment_id=yk["id"],
        idempotence_key=idem,
        status=PaymentStatus.pending,
        amount_kopecks=plan.amount_kopecks,
        currency="RUB",
        raw_payload=yk,
    )
    session.add(payment)
    confirmation_url = yk["confirmation"]["confirmation_url"]
    await session.flush()
    return order, payment, confirmation_url


async def start_stars_order(
    session: AsyncSession,
    *,
    plan_code: str,
    telegram_user_id: int,
    stars_amount: int,
) -> tuple[Order, Payment]:
    order = await create_order(
        session,
        plan_code=plan_code,
        provider=PaymentProvider.stars,
        telegram_user_id=telegram_user_id,
        deferred_activation=False,
        stars_amount=stars_amount,
    )
    idem = f"stars-{order.public_id}"
    payment = Payment(
        order_id=order.id,
        provider=PaymentProvider.stars,
        provider_payment_id=f"pending-{order.public_id}",
        idempotence_key=idem,
        status=PaymentStatus.pending,
        stars_amount=stars_amount,
        currency="XTR",
    )
    session.add(payment)
    await session.flush()
    return order, payment


async def finalize_stars_payment(
    session: AsyncSession,
    *,
    order_public_id: str,
    telegram_charge_id: str,
    stars_amount: int,
) -> tuple[Order, Any]:
    result = await session.execute(select(Order).where(Order.public_id == order_public_id))
    order = result.scalar_one()
    payment_result = await session.execute(select(Payment).where(Payment.order_id == order.id))
    payment = payment_result.scalars().first()
    if payment is None:
        raise ValueError("Payment missing for stars order")
    # Update provider id to charge id for uniqueness
    payment.provider_payment_id = telegram_charge_id
    return await mark_payment_succeeded(
        session,
        payment,
        stars_amount=stars_amount,
        currency="XTR",
        telegram_charge_id=telegram_charge_id,
        raw_payload={"telegram_payment_charge_id": telegram_charge_id},
    )


async def process_yookassa_notification(
    session: AsyncSession,
    client: YooKassaClient,
    *,
    event: dict[str, Any],
    settings: Settings | None = None,
) -> tuple[str, Order | None]:
    """Verify via API, then apply. Never trust webhook body alone for activation."""
    settings = settings or get_settings()
    event_type = event.get("event") or event.get("type")
    obj = event.get("object") or {}
    payment_id = obj.get("id")
    if not payment_id:
        return "ignored", None

    verified = await client.get_payment(payment_id)
    status = verified.get("status")
    metadata = verified.get("metadata") or {}
    order_public_id = metadata.get("order_public_id")

    result = await session.execute(
        select(Payment).where(
            Payment.provider == PaymentProvider.yookassa,
            Payment.provider_payment_id == payment_id,
        )
    )
    payment = result.scalar_one_or_none()
    if payment is None and order_public_id:
        order_result = await session.execute(
            select(Order).where(Order.public_id == order_public_id)
        )
        order = order_result.scalar_one_or_none()
        if order is None:
            return "unknown_order", None
        payment = Payment(
            order_id=order.id,
            provider=PaymentProvider.yookassa,
            provider_payment_id=payment_id,
            idempotence_key=make_idempotence_key(order.public_id) + f"-{payment_id}",
            status=PaymentStatus.pending,
            amount_kopecks=order.amount_kopecks,
            currency=order.currency,
        )
        session.add(payment)
        await session.flush()
    if payment is None:
        return "unknown_payment", None

    if status == "succeeded":
        amount = verified.get("amount") or {}
        kopecks = parse_amount_to_kopecks(amount)
        currency = amount.get("currency", "RUB")
        order, _grant = await mark_payment_succeeded(
            session,
            payment,
            amount_kopecks=kopecks,
            currency=currency,
            raw_payload=verified,
        )
        if order.status == OrderStatus.paid_unactivated:
            from app.models.entities import ActivationToken
            from app.services.jobs import enqueue_job

            existing_token = await session.execute(
                select(ActivationToken).where(ActivationToken.order_id == order.id)
            )
            if existing_token.scalar_one_or_none() is None:
                raw = await create_activation_token(session, order, settings=settings)
                # Store only in job payload for one-time delivery — not in logs
                await enqueue_job(
                    session,
                    "deliver_activation_token",
                    {"order_id": order.id, "token": raw},
                    unique_key=f"deliver-token:{order.id}",
                )
        return "succeeded", order

    if status == "canceled":
        if payment.status == PaymentStatus.pending:
            payment.status = PaymentStatus.canceled
            order = await session.get(Order, payment.order_id)
            if order and order.status == OrderStatus.pending:
                order.status = OrderStatus.canceled
            await session.flush()
        return "canceled", await session.get(Order, payment.order_id)

    if event_type and "refund" in str(event_type):
        refund_amount = obj.get("amount") or verified.get("refunded_amount") or {}
        if "value" in refund_amount:
            refunded = parse_amount_to_kopecks(refund_amount)
        else:
            refunded = payment.amount_kopecks or 0
        full = refunded >= (payment.amount_kopecks or 0)
        await reverse_grant_for_refund(
            session, payment, full=full, refunded_amount_kopecks=refunded
        )
        return "refunded", await session.get(Order, payment.order_id)

    return status or "ignored", await session.get(Order, payment.order_id)


async def reconcile_pending_yookassa(
    session: AsyncSession, client: YooKassaClient, *, settings: Settings | None = None
) -> int:
    result = await session.execute(
        select(Payment).where(
            Payment.provider == PaymentProvider.yookassa,
            Payment.status == PaymentStatus.pending,
        )
    )
    payments = list(result.scalars().all())
    processed = 0
    for payment in payments:
        try:
            verified = await client.get_payment(payment.provider_payment_id)
        except Exception:  # noqa: BLE001
            continue
        fake_event = {"event": f"payment.{verified.get('status')}", "object": verified}
        await process_yookassa_notification(
            session, client, event=fake_event, settings=settings
        )
        processed += 1
    return processed
