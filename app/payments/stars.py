from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.core.plans import PLANS


@dataclass(frozen=True, slots=True)
class StarsPlan:
    plan_code: str
    months: int
    xtr: int
    title: str


def available_stars_plans(settings: Settings | None = None) -> list[StarsPlan]:
    settings = settings or get_settings()
    if not settings.enable_stars:
        return []
    prices = settings.stars_prices
    result: list[StarsPlan] = []
    for code, plan in PLANS.items():
        xtr = prices.get(plan.months)
        if xtr:
            result.append(
                StarsPlan(plan_code=code, months=plan.months, xtr=xtr, title=plan.title)
            )
    return result


def stars_price_for_plan(plan_code: str, settings: Settings | None = None) -> int | None:
    settings = settings or get_settings()
    plan = PLANS[plan_code]
    return settings.stars_prices.get(plan.months)
