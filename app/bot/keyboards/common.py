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
        [InlineKeyboardButton(text="Моя подписка", callback_data="menu:status")],
    ]
    if active:
        rows.append([InlineKeyboardButton(text="Войти в канал", callback_data="menu:enter")])
    rows.append([InlineKeyboardButton(text="Услуги", callback_data="menu:services")])
    rows.append(
        [
            InlineKeyboardButton(
                text="FAQ и служба поддержки",
                callback_data="menu:faq",
            )
        ]
    )
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


def faq_kb(settings: Settings) -> InlineKeyboardMarkup:
    support = manager_contact_url(settings)
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="Оферта", url=settings.offer_url)],
        [
            InlineKeyboardButton(
                text="Политика конфиденциальности",
                url=settings.privacy_url,
            )
        ],
        [InlineKeyboardButton(text="Написать в поддержку @kovalg29", url=support)],
    ]
    if settings.paysupport_url:
        rows.append(
            [InlineKeyboardButton(text="Поддержка по оплате", url=settings.paysupport_url)]
        )
    rows.append([InlineKeyboardButton(text="« Назад", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def docs_kb(settings: Settings) -> InlineKeyboardMarkup:
    """Backward-compatible alias for FAQ/docs links."""
    return faq_kb(settings)


def subscribe_plans_kb(settings: Settings) -> InlineKeyboardMarkup:
    """Show calendar-month tariffs with RUB prices only (no XTR in labels)."""
    rows: list[list[InlineKeyboardButton]] = []
    stars = {p.plan_code: p for p in available_stars_plans(settings)}
    for code, plan in PLANS.items():
        label = f"{plan.title} — {format_rub(plan.amount_kopecks)}"
        if code in stars:
            # Backend may still charge Stars; UI shows RUB only.
            rows.append(
                [InlineKeyboardButton(text=label, callback_data=f"stars:{code}")]
            )
        elif settings.enable_web_yookassa:
            url = f"{settings.app_base_url.rstrip('/')}/checkout?plan={code}"
            rows.append([InlineKeyboardButton(text=f"{label} (сайт)", url=url)])
        elif settings.enable_bot_initiated_yookassa and not settings.is_production:
            rows.append(
                [InlineKeyboardButton(text=f"{label} (dev)", callback_data=f"ykbot:{code}")]
            )
        else:
            # No pay adapter — still list tariff; contact manager.
            rows.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        url=manager_contact_url(settings),
                    )
                ]
            )
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
