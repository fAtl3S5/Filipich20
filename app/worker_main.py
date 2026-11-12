"""Standalone durable job worker process."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.jobs.worker import NullNotifier, worker_loop
from app.services.access import NullTelegramAccessClient


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    access_client: object = NullTelegramAccessClient()
    notifier: object = NullNotifier()
    if settings.bot_token:
        from app.bot.factory import create_bot
        from app.bot.notifier import AiogramNotifier
        from app.bot.tg_access import AiogramAccessClient

        bot = create_bot(settings)
        access_client = AiogramAccessClient(bot)
        notifier = AiogramNotifier(bot, settings)
    await worker_loop(access_client=access_client, notifier=notifier, settings=settings)  # type: ignore[arg-type]


if __name__ == "__main__":
    asyncio.run(main())
