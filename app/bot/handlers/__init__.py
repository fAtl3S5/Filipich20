from aiogram import Router

from app.bot.handlers import admin, chat_gates, menu, payments_stars, support


def setup_routers() -> Router:
    root = Router()
    root.include_router(menu.router)
    root.include_router(payments_stars.router)
    root.include_router(support.router)
    root.include_router(admin.router)
    root.include_router(chat_gates.router)
    return root
