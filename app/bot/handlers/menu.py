from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import (
    contact_manager_kb,
    enter_channel_kb,
    faq_kb,
    main_menu_kb,
    services_kb,
    subscribe_plans_kb,
)
from app.bot.texts import (
    FAQ_INTRO,
    ONLINE_MEETING_TEXT,
    SERVICES_INTRO,
    START_TEXT,
    SUBSCRIBE_INTRO,
    VIDEO_GREETING_TEXT,
)
from app.core.config import Settings
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
    # RUB tariffs + one-time wording only; no XTR amounts in user copy.
    return SUBSCRIBE_INTRO


@router.message(Command("subscribe", "buy"))
async def cmd_subscribe(message: Message, settings: Settings) -> None:
    await message.answer(_subscribe_text(settings), reply_markup=subscribe_plans_kb(settings))


@router.message(Command("services"))
async def cmd_services(message: Message) -> None:
    await message.answer(SERVICES_INTRO, reply_markup=services_kb())


@router.message(Command("video"))
async def cmd_video(message: Message, settings: Settings) -> None:
    await message.answer(
        VIDEO_GREETING_TEXT,
        reply_markup=contact_manager_kb(settings),
    )


@router.message(Command("meeting"))
async def cmd_meeting(message: Message, settings: Settings) -> None:
    await message.answer(
        ONLINE_MEETING_TEXT,
        reply_markup=contact_manager_kb(settings),
    )


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


@router.message(Command("faq"))
async def cmd_faq(message: Message, settings: Settings) -> None:
    await message.answer(FAQ_INTRO, reply_markup=faq_kb(settings), disable_web_page_preview=True)


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


@router.callback_query(F.data == "menu:services")
async def cb_services(query: CallbackQuery) -> None:
    await query.message.edit_text(SERVICES_INTRO, reply_markup=services_kb())  # type: ignore[union-attr]
    await query.answer()


@router.callback_query(F.data == "service:video")
async def cb_service_video(query: CallbackQuery, settings: Settings) -> None:
    await query.message.edit_text(  # type: ignore[union-attr]
        VIDEO_GREETING_TEXT,
        reply_markup=contact_manager_kb(settings),
    )
    await query.answer()


@router.callback_query(F.data == "service:meeting")
async def cb_service_meeting(query: CallbackQuery, settings: Settings) -> None:
    await query.message.edit_text(  # type: ignore[union-attr]
        ONLINE_MEETING_TEXT,
        reply_markup=contact_manager_kb(settings),
    )
    await query.answer()


@router.callback_query(F.data.in_({"menu:faq", "menu:docs", "menu:support"}))
async def cb_faq(query: CallbackQuery, settings: Settings) -> None:
    await query.message.edit_text(  # type: ignore[union-attr]
        FAQ_INTRO,
        reply_markup=faq_kb(settings),
        disable_web_page_preview=True,
    )
    await query.answer()
