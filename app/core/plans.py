from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Plan:
    code: str
    months: int
    amount_kopecks: int
    title: str


PLANS: dict[str, Plan] = {
    "1m": Plan(code="1m", months=1, amount_kopecks=99_000, title="1 месяц"),
    "3m": Plan(code="3m", months=3, amount_kopecks=269_000, title="3 месяца"),
    "6m": Plan(code="6m", months=6, amount_kopecks=499_000, title="6 месяцев"),
    "12m": Plan(code="12m", months=12, amount_kopecks=899_000, title="12 месяцев"),
}


def get_plan(code: str) -> Plan:
    try:
        return PLANS[code]
    except KeyError as exc:
        raise ValueError(f"Unknown plan: {code}") from exc


def format_rub(kopecks: int) -> str:
    rub = kopecks // 100
    kop = kopecks % 100
    return f"{rub}₽" if kop == 0 else f"{rub},{kop:02d}₽"
