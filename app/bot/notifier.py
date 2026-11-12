from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.config import Settings
from app.models.entities import Broadcast


class AiogramNotifier:
    def __init__(self, bot: Bot, settings: Settings) -> None:
        self.bot = bot
        self.settings = settings

    async def send_message(
        self, telegram_user_id: int, text: str, reply_markup=None
    ) -> None:
        try:
            await self.bot.send_message(telegram_user_id, text, reply_markup=reply_markup)
        except TelegramForbiddenError as exc:
            raise RuntimeError("blocked by user") from exc

    async def send_broadcast_item(self, telegram_user_id: int, broadcast: Broadcast) -> None:
        kb = None
        if broadcast.buttons_json:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=b["text"], url=b["url"])]
                    for b in broadcast.buttons_json
                ]
            )
        try:
            if broadcast.media_type == "photo" and broadcast.media_file_id:
                await self.bot.send_photo(
                    telegram_user_id,
                    broadcast.media_file_id,
                    caption=broadcast.text,
                    reply_markup=kb,
                )
            elif broadcast.media_type == "video" and broadcast.media_file_id:
                await self.bot.send_video(
                    telegram_user_id,
                    broadcast.media_file_id,
                    caption=broadcast.text,
                    reply_markup=kb,
                )
            else:
                await self.bot.send_message(telegram_user_id, broadcast.text, reply_markup=kb)
        except TelegramRetryAfter as exc:
            raise RuntimeError(f"retry_after:{exc.retry_after}") from exc
        except TelegramForbiddenError as exc:
            raise RuntimeError("blocked by user") from exc

    async def notify_admins(self, text: str) -> None:
        for admin_id in self.settings.admin_ids:
            try:
                await self.bot.send_message(admin_id, text)
            except Exception:  # noqa: BLE001
                pass
