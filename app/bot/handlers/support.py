from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.services.support import create_support_ticket
from app.services.users import get_or_create_user

router = Router(name="support")

_waiting_support: set[int] = set()


@router.message(Command("support"))
async def cmd_support(message: Message, settings: Settings) -> None:
    assert message.from_user
    if settings.support_url:
        await message.answer(f"Поддержка: {settings.support_url}")
        return
    _waiting_support.add(message.from_user.id)
    await message.answer("Опишите вопрос одним сообщением.")


@router.message(Command("terms"))
async def cmd_terms(message: Message, settings: Settings) -> None:
    url = settings.terms_url or "Условия использования будут опубликованы владельцем."
    await message.answer(f"Условия: {url}")


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message, settings: Settings) -> None:
    url = settings.paysupport_url or settings.support_url
    if url:
        await message.answer(f"Поддержка по оплате: {url}")
    else:
        _waiting_support.add(message.from_user.id)  # type: ignore[union-attr]
        await message.answer(
            "Напишите вопрос по оплате одним сообщением. "
            "Telegram Support не поможет с покупками через этого бота."
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
