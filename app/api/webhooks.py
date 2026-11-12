from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.checkout import ensure_activation_token_for_order, store_activation_token
from app.api.deps import get_yookassa
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.security import constant_time_equals
from app.models.entities import OrderStatus
from app.services.payments import process_yookassa_notification

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/yookassa")
async def yookassa_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    payload: dict[str, Any] = await request.json()
    client = get_yookassa()
    status, order = await process_yookassa_notification(
        session, client, event=payload, settings=settings
    )
    if order and order.status == OrderStatus.paid_unactivated:
        raw = await ensure_activation_token_for_order(session, order, settings)
        store_activation_token(order.id, raw)
    await session.commit()
    return {"status": status}


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    if settings.telegram_webhook_secret:
        if not x_telegram_bot_api_secret_token or not constant_time_equals(
            x_telegram_bot_api_secret_token, settings.telegram_webhook_secret
        ):
            raise HTTPException(status_code=403, detail="Bad secret_token")
    update = await request.json()
    bot = request.app.state.bot
    dp = request.app.state.dispatcher
    if bot is None or dp is None:
        raise HTTPException(status_code=503, detail="Bot not configured")
    from aiogram.types import Update

    await dp.feed_update(bot, Update.model_validate(update))
    return {"ok": True}
