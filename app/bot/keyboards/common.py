from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.config import Settings
from app.core.plans import PLANS, format_rub
from app.payments.stars import available_stars_plans


def manager_contact_url(settings: Settings) -> str:
    return (settings.support_url or "https://t.me/kovalg29").strip()


def main_menu_kb(*, active: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Оформить подписку", callback_data="menu:subscribe")],
        [InlineKeyboardButton(text="Услуги", callback_data="menu:services")],
        [InlineKeyboardButton(text="Моя подписка", callback_data="menu:status")],
    ]
    if active:
        rows.append([InlineKeyboardButton(text="Войти в канал", callback_data="menu:enter")])
    rows.append([InlineKeyboardButton(text="Документы", callback_data="menu:docs")])
    rows.append([InlineKeyboardButton(text="Поддержка", callback_data="menu:support")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def services_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Видеопривет — 1 990 ₽", callback_data="service:video")],
            [
                InlineKeyboardButton(
                    text="Онлайн-встреча — 3 990 ₽",
                    callback_data="service:meeting",
                )
            ],
            [InlineKeyboardButton(text="« Назад", callback_data="menu:home")],
        ]
    )


def contact_manager_kb(settings: Settings, *, back: str = "menu:services") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Связаться с менеджером",
                    url=manager_contact_url(settings),
                )
            ],
            [InlineKeyboardButton(text="« Назад", callback_data=back)],
        ]
    )


def docs_kb(settings: Settings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оферта", url=settings.offer_url)],
            [
                InlineKeyboardButton(
                    text="Политика конфиденциальности",
                    url=settings.privacy_url,
                )
            ],
            [InlineKeyboardButton(text="« Назад", callback_data="menu:home")],
        ]
    )


def subscribe_plans_kb(settings: Settings) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    stars = {p.plan_code: p for p in available_stars_plans(settings)}
    for code, plan in PLANS.items():
        buttons: list[InlineKeyboardButton] = []
        if settings.enable_web_yookassa:
            # Independent web checkout — open URL, not Telegram Payments
            url = f"{settings.app_base_url.rstrip('/')}/checkout?plan={code}"
            buttons.append(
                InlineKeyboardButton(
                    text=f"{plan.title} — {format_rub(plan.amount_kopecks)} (сайт)",
                    url=url,
                )
            )
        if code in stars:
            buttons.append(
                InlineKeyboardButton(
                    text=f"{plan.title} — {stars[code].xtr} ⭐ (тест)",
                    callback_data=f"stars:{code}",
                )
            )
        if settings.enable_bot_initiated_yookassa and not settings.is_production:
            buttons.append(
                InlineKeyboardButton(
                    text=f"{plan.title} — ЮKassa (dev)",
                    callback_data=f"ykbot:{code}",
                )
            )
        for b in buttons:
            rows.append([b])
    rows.append([InlineKeyboardButton(text="« Назад", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def enter_channel_kb(invite_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Войти в канал", url=invite_link)],
        ]
    )


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Статистика", callback_data="admin:stats")],
            [InlineKeyboardButton(text="Истекающие (3д)", callback_data="admin:expiring")],
            [InlineKeyboardButton(text="Ошибки задач", callback_data="admin:jobs")],
            [InlineKeyboardButton(text="Диагностика прав", callback_data="admin:diag")],
        ]
    )
