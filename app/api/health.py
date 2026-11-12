from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    db_ok = False
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "db": False, "error": str(exc)}
    payload = {"status": "ok", "db": db_ok, "env": settings.app_env}
    if settings.is_production:
        missing = settings.production_missing_env()
        payload["production_ready"] = not missing
        payload["missing_env"] = missing
    return payload
