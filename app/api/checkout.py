from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_yookassa
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.plans import PLANS, format_rub
from app.core.security import verify_telegram_login
from app.core.timeutil import utcnow
from app.models.entities import Order
from app.services.payments import start_yookassa_checkout
from app.services.subscriptions import activate_order_for_user, create_activation_token

router = APIRouter(tags=["checkout"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))

# Ephemeral map order_id -> raw token for status page (also delivered via job in prod flows)
_ACTIVATION_TOKENS: dict[int, str] = {}


@router.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "home.html")


@router.get("/checkout", response_class=HTMLResponse)
async def checkout_page(
    request: Request,
    plan: str = Query(default="1m"),
    tg: int | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    plans = [
        {"code": p.code, "title": p.title, "price_label": format_rub(p.amount_kopecks)}
        for p in PLANS.values()
    ]
    return templates.TemplateResponse(
        request,
        "checkout.html",
        {
            "plans": plans,
            "selected": plan if plan in PLANS else "1m",
            "telegram_user_id": tg,
            "telegram_login_bot": settings.telegram_login_bot_username,
            "app_base_url": settings.app_base_url.rstrip("/"),
            "enable_web_yookassa": settings.enable_web_yookassa,
            "error": None,
        },
    )


@router.post("/checkout/create", response_class=HTMLResponse)
async def checkout_create(
    request: Request,
    plan: str = Form(...),
    telegram_user_id: str = Form(default=""),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    if not settings.enable_web_yookassa:
        return HTMLResponse("Веб-оплата ЮKассой отключена", status_code=403)
    tid = int(telegram_user_id) if telegram_user_id.strip().isdigit() else None
    # Never trust client-supplied tg id for granting without Login Widget;
    # if provided without verified login cookie, force deferred activation.
    verified = request.session.get("tg_verified_id") if hasattr(request, "session") else None
    if tid is not None and verified != tid:
        # Treat as hint only → deferred
        deferred = True
        bound_tid = None
    else:
        deferred = tid is None
        bound_tid = tid

    client = get_yookassa()
    order, _payment, url = await start_yookassa_checkout(
        session,
        client,
        plan_code=plan,
        telegram_user_id=bound_tid,
        settings=settings,
        deferred=deferred or bound_tid is None,
    )
    await session.commit()
    return templates.TemplateResponse(
        request,
        "checkout_pending.html",
        {"order_public_id": order.public_id, "confirmation_url": url},
    )


@router.get("/checkout/return")
async def checkout_return(order_public_id: str | None = None) -> RedirectResponse:
    # return_url must NOT activate — redirect to status only
    target = f"/checkout/status/{order_public_id}" if order_public_id else "/checkout"
    return RedirectResponse(target)


@router.get("/checkout/status/{order_public_id}", response_class=HTMLResponse)
async def checkout_status(
    request: Request,
    order_public_id: str,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    result = await session.execute(select(Order).where(Order.public_id == order_public_id))
    order = result.scalar_one_or_none()
    if order is None:
        return HTMLResponse("Заказ не найден", status_code=404)
    token = _ACTIVATION_TOKENS.get(order.id)
    activation_link = None
    if token and settings.telegram_login_bot_username:
        activation_link = f"https://t.me/{settings.telegram_login_bot_username}?start=activate_{token}"
    elif token:
        activation_link = None
    return templates.TemplateResponse(
        request,
        "checkout_status.html",
        {
            "order": order,
            "activation_token": token,
            "activation_link": activation_link,
        },
    )


@router.get("/checkout/telegram-login")
async def telegram_login(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    data = dict(request.query_params)
    ok = verify_telegram_login(
        data,
        bot_token=settings.bot_token,
        max_age_sec=settings.telegram_login_auth_date_max_age,
        now_ts=int(utcnow().timestamp()),
    )
    if not ok:
        return RedirectResponse("/checkout?error=login")
    tg_id = int(data["id"])
    # Store verified id in a signed-less cookie via query redirect for checkout
    # Prefer activating unpaid binding on an order if provided
    order_id = data.get("order")
    if order_id:
        result = await session.execute(select(Order).where(Order.public_id == order_id))
        order = result.scalar_one_or_none()
        if order is not None:
            await activate_order_for_user(session, order, tg_id)
            await session.commit()
            return RedirectResponse(f"/checkout/status/{order.public_id}")
    return RedirectResponse(f"/checkout?tg={tg_id}&verified=1")


def store_activation_token(order_id: int, raw: str) -> None:
    _ACTIVATION_TOKENS[order_id] = raw


async def ensure_activation_token_for_order(
    session: AsyncSession, order: Order, settings: Settings
) -> str:
    if order.id in _ACTIVATION_TOKENS:
        return _ACTIVATION_TOKENS[order.id]
    raw = await create_activation_token(session, order, settings=settings)
    store_activation_token(order.id, raw)
    return raw
