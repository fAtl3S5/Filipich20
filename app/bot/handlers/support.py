from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import faq_kb
from app.bot.texts import FAQ_INTRO
from app.core.config import Settings
from app.services.support import create_support_ticket
from app.services.users import get_or_create_user

router = Router(name="support")

_waiting_support: set[int] = set()


@router.message(Command("support"))
async def cmd_support(message: Message, settings: Settings) -> None:
    assert message.from_user
    await message.answer(
        FAQ_INTRO,
        reply_markup=faq_kb(settings),
        disable_web_page_preview=True,
    )


@router.message(Command("terms", "offer", "docs"))
async def cmd_terms(message: Message, settings: Settings) -> None:
    await message.answer(
        FAQ_INTRO,
        reply_markup=faq_kb(settings),
        disable_web_page_preview=True,
    )


@router.message(Command("privacy"))
async def cmd_privacy(message: Message, settings: Settings) -> None:
    await message.answer(
        f"Политика конфиденциальности:\n{settings.privacy_url}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Открыть ПК", url=settings.privacy_url)],
                [InlineKeyboardButton(text="Оферта", url=settings.offer_url)],
            ]
        ),
        disable_web_page_preview=True,
    )


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message, settings: Settings) -> None:
    """Telegram may expect /paysupport; same FAQ + one support button as /support."""
    assert message.from_user
    await message.answer(
        FAQ_INTRO,
        reply_markup=faq_kb(settings),
        disable_web_page_preview=True,
    )


@router.message(F.text & ~F.text.startswith("/"))
async def on_text(
    message: Message, session: AsyncSession, settings: Settings, bot
) -> None:
    assert message.from_user and message.text
    if message.from_user.id not in _waiting_support:
        return
    _waiting_support.discard(message.from_user.id)
    user = await get_or_create_user(session, message.from_user.id, mark_started=True)
    ticket = await create_support_ticket(session, user, message.text)
    await message.answer(f"Обращение {ticket.public_number} принято.")
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(
                admin_id,
                f"Поддержка {ticket.public_number}\n"
                f"user={user.telegram_user_id} @{user.username or '—'}\n\n{message.text}",
            )
        except Exception:  # noqa: BLE001
            pass
