"""Telegram Bot API command menu (setMyCommands)."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault

logger = logging.getLogger(__name__)

# Shown in the Telegram chat «Menu» / «/» suggestions.
BOT_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Начать"),
    BotCommand(command="subscribe", description="Оформить подписку"),
    BotCommand(command="buy", description="Купить подписку"),
    BotCommand(command="services", description="Услуги"),
    BotCommand(command="status", description="Моя подписка"),
    BotCommand(command="enter", description="Войти в канал"),
    BotCommand(command="faq", description="FAQ и поддержка"),
    BotCommand(command="terms", description="Оферта"),
    BotCommand(command="paysupport", description="Поддержка по оплате"),
    BotCommand(command="support", description="Поддержка"),
]


async def set_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeDefault())
    logger.info(
        "setMyCommands: %s",
        ", ".join(f"/{c.command}" for c in BOT_COMMANDS),
    )
