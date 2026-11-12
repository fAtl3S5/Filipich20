from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import enter_channel_kb, main_menu_kb, subscribe_plans_kb
from app.bot.texts import (
    DEFERRED_NOTE,
    ONE_TIME_NOTE,
    START_TEXT,
    STARS_TEST_NOTE,
    SUBSCRIBE_INTRO,
)
from app.payments.stars import available_stars_plans
from app.core.config import Settings, get_settings
from app.services.access import TelegramAccessClient, create_channel_invite, provision_access
from app.services.subscriptions import activate_order_with_token, subscription_status_text
from app.services.users import get_or_create_user, is_subscription_active

router = Router(name="menu")


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, settings: Settings) -> None:
    assert message.from_user
    args = message.text.split(maxsplit=1)[1] if message.text and " " in message.text else ""
    user = await get_or_create_user(
        session,
        message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        language_code=message.from_user.language_code,
        mark_started=True,
    )
    if args.startswith("activate_"):
        token = args.removeprefix("activate_")
        try:
            await activate_order_with_token(
                session, raw_token=token, telegram_user_id=message.from_user.id, settings=settings
            )
            await message.answer(
                "Активация успешна. Доступ к закрытому каналу и комментариям открыт.",
                reply_markup=main_menu_kb(active=True),
            )
            return
        except ValueError as exc:
            await message.answer(str(exc), reply_markup=main_menu_kb(active=False))
            return

    active = is_subscription_active(user)
    if active:
        await message.answer(
            subscription_status_text(user, settings),
            reply_markup=main_menu_kb(active=True),
        )
    else:
        await message.answer(START_TEXT, reply_markup=main_menu_kb(active=False))


def _subscribe_text(settings: Settings) -> str:
    text = f"{SUBSCRIBE_INTRO}\n\n{ONE_TIME_NOTE}\n\n{DEFERRED_NOTE}"
    if available_stars_plans(settings):
        text += f"\n\n{STARS_TEST_NOTE}"
    elif settings.enable_stars:
        text += "\n\nТарифы Stars пока не заданы (нужны STARS_PRICE_*)."
    if not settings.enable_web_yookassa:
        text += "\n\nОплата картой на сайте сейчас выключена."
    if settings.enable_bot_initiated_yookassa and settings.is_production:
        text += (
            "\n\n⚠ В production оплата ЮKассой из бота отключена "
            "(цифровой доступ внутри Telegram = Stars)."
        )
    return text


@router.message(Command("subscribe", "buy"))
async def cmd_subscribe(message: Message, settings: Settings) -> None:
    await message.answer(_subscribe_text(settings), reply_markup=subscribe_plans_kb(settings))


@router.message(Command("status"))
async def cmd_status(message: Message, session: AsyncSession, settings: Settings) -> None:
    assert message.from_user
    user = await get_or_create_user(session, message.from_user.id, mark_started=True)
    active = is_subscription_active(user)
    await message.answer(
        subscription_status_text(user, settings),
        reply_markup=main_menu_kb(active=active),
    )


@router.message(Command("enter"))
async def cmd_enter(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    access_client: TelegramAccessClient,
) -> None:
    assert message.from_user
    user = await get_or_create_user(session, message.from_user.id, mark_started=True)
    if not is_subscription_active(user):
        await message.answer(
            "Нет активной подписки. Оформите доступ командой /subscribe.",
            reply_markup=main_menu_kb(active=False),
        )
        return
    await provision_access(session, access_client, message.from_user.id, settings=settings)
    try:
        link = await create_channel_invite(
            session, access_client, message.from_user.id, settings=settings
        )
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"Не удалось создать ссылку: {exc}")
        return
    await message.answer(
        "Одна кнопка — вход в канал. Комментарии — под постами.",
        reply_markup=enter_channel_kb(link),
    )


@router.callback_query(F.data == "menu:home")
async def cb_home(query: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    assert query.from_user
    user = await get_or_create_user(session, query.from_user.id, mark_started=True)
    active = is_subscription_active(user)
    text = subscription_status_text(user, settings) if active else START_TEXT
    await query.message.edit_text(text, reply_markup=main_menu_kb(active=active))  # type: ignore[union-attr]
    await query.answer()


@router.callback_query(F.data == "menu:subscribe")
async def cb_subscribe(query: CallbackQuery, settings: Settings) -> None:
    await query.message.edit_text(  # type: ignore[union-attr]
        _subscribe_text(settings),
        reply_markup=subscribe_plans_kb(settings),
    )
    await query.answer()


@router.callback_query(F.data == "menu:status")
async def cb_status(query: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    assert query.from_user
    user = await get_or_create_user(session, query.from_user.id, mark_started=True)
    active = is_subscription_active(user)
    await query.message.edit_text(  # type: ignore[union-attr]
        subscription_status_text(user, settings),
        reply_markup=main_menu_kb(active=active),
    )
    await query.answer()


@router.callback_query(F.data == "menu:enter")
async def cb_enter(
    query: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
    access_client: TelegramAccessClient,
) -> None:
    assert query.from_user
    user = await get_or_create_user(session, query.from_user.id, mark_started=True)
    if not is_subscription_active(user):
        await query.answer("Нет активной подписки", show_alert=True)
        return
    await provision_access(session, access_client, query.from_user.id, settings=settings)
    try:
        link = await create_channel_invite(
            session, access_client, query.from_user.id, settings=settings
        )
    except Exception as exc:  # noqa: BLE001
        await query.answer(f"Не удалось создать ссылку: {exc}", show_alert=True)
        return
    await query.message.answer(  # type: ignore[union-attr]
        "Одна кнопка — вход в канал. Комментарии — под постами.",
        reply_markup=enter_channel_kb(link),
    )
    await query.answer()


@router.callback_query(F.data == "menu:support")
async def cb_support(query: CallbackQuery, settings: Settings) -> None:
    from app.bot.texts import SUPPORT_FALLBACK

    if settings.support_url:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Написать в поддержку", url=settings.support_url)],
                [InlineKeyboardButton(text="« Назад", callback_data="menu:home")],
            ]
        )
        await query.message.edit_text("Поддержка:", reply_markup=kb)  # type: ignore[union-attr]
    else:
        await query.message.edit_text(  # type: ignore[union-attr]
            SUPPORT_FALLBACK,
            reply_markup=main_menu_kb(),
        )
    await query.answer()
