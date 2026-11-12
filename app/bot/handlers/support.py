from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import docs_kb
from app.core.config import Settings
from app.services.support import create_support_ticket
from app.services.users import get_or_create_user

router = Router(name="support")

_waiting_support: set[int] = set()


@router.message(Command("support"))
async def cmd_support(message: Message, settings: Settings) -> None:
    assert message.from_user
    from app.bot.keyboards.common import manager_contact_url

    support = manager_contact_url(settings)
    if support:
        await message.answer(
            f"Поддержка: {support}\nМенеджер: @kovalg29",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Написать @kovalg29", url=support)]
                ]
            ),
            disable_web_page_preview=True,
        )
        return
    _waiting_support.add(message.from_user.id)
    await message.answer("Опишите вопрос одним сообщением.")


@router.message(Command("terms", "offer", "docs"))
async def cmd_terms(message: Message, settings: Settings) -> None:
    await message.answer(
        "Документы:\n"
        f"Оферта: {settings.offer_url}\n"
        f"Политика конфиденциальности: {settings.privacy_url}",
        reply_markup=docs_kb(settings),
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
    assert message.from_user
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Поддержка по оплате", url=settings.paysupport_url)],
            [InlineKeyboardButton(text="Оферта", url=settings.offer_url)],
            [
                InlineKeyboardButton(
                    text="Политика конфиденциальности",
                    url=settings.privacy_url,
                )
            ],
        ]
    )
    await message.answer(
        "Вопросы по оплате Stars / доступу:\n"
        f"{settings.paysupport_url}\n\n"
        "Или напишите сюда одним сообщением — создадим обращение.",
        reply_markup=kb,
        disable_web_page_preview=True,
    )
    _waiting_support.add(message.from_user.id)


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
