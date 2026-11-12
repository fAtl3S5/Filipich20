from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import admin_api, checkout, health, legal, webhooks
from app.core.config import get_settings
from app.jobs.worker import NullNotifier, worker_loop
from app.services.access import NullTelegramAccessClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=logging.INFO)
    app.state.bot = None
    app.state.dispatcher = None
    app.state.worker_task = None
    app.state.stop_event = asyncio.Event()

    access_client = NullTelegramAccessClient()
    notifier = NullNotifier()

    if settings.bot_token:
        from app.bot.factory import create_bot, create_dispatcher
        from app.bot.notifier import AiogramNotifier
        from app.bot.tg_access import AiogramAccessClient

        bot = create_bot(settings)
        dp = create_dispatcher(settings, bot)
        app.state.bot = bot
        app.state.dispatcher = dp
        access_client = AiogramAccessClient(bot)
        notifier = AiogramNotifier(bot, settings)
        from app.bot.commands import set_bot_commands

        try:
            await set_bot_commands(bot)
        except Exception:  # noqa: BLE001
            logger.exception("setMyCommands failed")

        if settings.app_env == "local" and not settings.is_production:
            # Optional polling in local if webhook not used — disabled by default in compose
            pass

    app.state.access_client = access_client
    app.state.notifier = notifier
    app.state.worker_task = asyncio.create_task(
        worker_loop(
            access_client=access_client,
            notifier=notifier,
            settings=settings,
            stop_event=app.state.stop_event,
        )
    )
    if settings.is_production:
        missing = settings.production_missing_env()
        if missing:
            logger.error("Production missing env: %s", missing)

    yield

    app.state.stop_event.set()
    if app.state.worker_task:
        app.state.worker_task.cancel()
        try:
            await app.state.worker_task
        except asyncio.CancelledError:
            pass
    if app.state.bot:
        await app.state.bot.session.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Филипп ещё расскажет — подписка", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(checkout.router)
    app.include_router(legal.router)
    app.include_router(webhooks.router)
    app.include_router(webhooks.root_webhook_router)
    app.include_router(admin_api.router)
    static_dir = __import__("pathlib").Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return app


app = create_app()
