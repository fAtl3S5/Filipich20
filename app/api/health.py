from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session

router = APIRouter(tags=["health"])


async def _health_payload(
    session: AsyncSession,
    settings: Settings,
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


@router.get("/healthz")
async def healthz(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    return await _health_payload(session, settings)


@router.get("/health")
async def health_bothost(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Bothost-friendly alias for /healthz."""
    return await _health_payload(session, settings)
