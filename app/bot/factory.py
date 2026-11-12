from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import setup_routers
from app.bot.middlewares.db import DbSessionMiddleware
from app.bot.tg_access import AiogramAccessClient
from app.core.config import Settings


def create_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(settings: Settings, bot: Bot) -> Dispatcher:
    dp = Dispatcher()
    dp["settings"] = settings
    dp["access_client"] = AiogramAccessClient(bot)
    dp.update.middleware(DbSessionMiddleware())

    @dp.update.outer_middleware()
    async def inject_deps(handler, event, data):
        data.setdefault("settings", settings)
        data.setdefault("access_client", dp["access_client"])
        data.setdefault("bot", bot)
        return await handler(event, data)

    dp.include_router(setup_routers())
    return dp
