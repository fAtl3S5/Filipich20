from __future__ import annotations

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.plans import get_plan
from app.payments.stars import stars_price_for_plan
from app.services.payments import finalize_stars_payment, start_stars_order

router = Router(name="payments_stars")


@router.callback_query(F.data.startswith("stars:"))
async def cb_stars(query: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    assert query.from_user and query.message
    if not settings.enable_stars:
        await query.answer("Оплата Stars отключена", show_alert=True)
        return
    plan_code = query.data.split(":", 1)[1]  # type: ignore[union-attr]
    xtr = stars_price_for_plan(plan_code, settings)
    if not xtr:
        await query.answer(
            "Цена в Stars не задана владельцем. Выберите оплату на сайте.",
            show_alert=True,
        )
        return
    plan = get_plan(plan_code)
    order, _payment = await start_stars_order(
        session,
        plan_code=plan_code,
        telegram_user_id=query.from_user.id,
        stars_amount=xtr,
    )
    await query.message.answer_invoice(  # type: ignore[union-attr]
        title=f"Подписка {plan.title}",
        description="Доступ к закрытому каналу и комментариям. Разовая оплата.",
        payload=order.public_id,
        currency="XTR",
        prices=[LabeledPrice(label=plan.title, amount=xtr)],
        provider_token="",  # Stars: empty provider token
    )
    await query.answer()


@router.callback_query(F.data.startswith("ykbot:"))
async def cb_yk_bot(query: CallbackQuery, settings: Settings) -> None:
    """Dev-only path. Production must keep ENABLE_BOT_INITIATED_YOOKASSA=false."""
    if settings.is_production or not settings.enable_bot_initiated_yookassa:
        await query.answer(
            "ЮKасса из бота отключена. Используйте оплату на сайте или Stars.",
            show_alert=True,
        )
        return
    plan_code = query.data.split(":", 1)[1]  # type: ignore[union-attr]
    url = f"{settings.app_base_url.rstrip('/')}/checkout?plan={plan_code}&tg={query.from_user.id}"  # type: ignore[union-attr]
    await query.answer()
    await query.message.answer(f"Dev checkout: {url}")  # type: ignore[union-attr]


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery, session: AsyncSession, settings: Settings) -> None:
    from sqlalchemy import select
    from app.models.entities import Order, OrderStatus

    result = await session.execute(select(Order).where(Order.public_id == query.invoice_payload))
    order = result.scalar_one_or_none()
    if order is None or order.status != OrderStatus.pending:
        await query.answer(ok=False, error_message="Заказ недоступен")
        return
    expected = stars_price_for_plan(order.plan_code, settings)
    if expected is None or query.total_amount != expected:
        await query.answer(ok=False, error_message="Неверная сумма")
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, session: AsyncSession) -> None:
    assert message.successful_payment
    sp = message.successful_payment
    await finalize_stars_payment(
        session,
        order_public_id=sp.invoice_payload,
        telegram_charge_id=sp.telegram_payment_charge_id,
        stars_amount=sp.total_amount,
    )
    await message.answer(
        "Оплата Stars получена. Доступ к закрытому каналу и комментариям активирован.\n"
        "Нажмите «Войти в канал» в меню."
    )
