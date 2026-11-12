from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import Settings, get_settings

router = APIRouter(tags=["legal"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))

PUBLISHED = "12.11.2026"


@router.get("/legal", response_class=HTMLResponse)
async def legal_index(request: Request, settings: Settings = Depends(get_settings)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "legal_index.html",
        {
            "title": "Документы",
            "subtitle": "Оферта и политика конфиденциальности",
            "app_base_url": settings.app_base_url.rstrip("/"),
            "published": PUBLISHED,
        },
    )


@router.get("/legal/offer", response_class=HTMLResponse)
async def legal_offer(request: Request, settings: Settings = Depends(get_settings)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "legal_offer.html",
        {
            "title": "Публичная оферта",
            "subtitle": "Договор на доступ к каналу «Филипп расскажет»",
            "app_base_url": settings.app_base_url.rstrip("/"),
            "published": PUBLISHED,
        },
    )


@router.get("/legal/privacy", response_class=HTMLResponse)
async def legal_privacy(request: Request, settings: Settings = Depends(get_settings)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "legal_privacy.html",
        {
            "title": "Политика конфиденциальности",
            "subtitle": "Обработка данных пользователей сервиса",
            "app_base_url": settings.app_base_url.rstrip("/"),
            "published": PUBLISHED,
        },
    )


@router.get("/terms")
async def terms_redirect() -> RedirectResponse:
    return RedirectResponse("/legal/offer", status_code=302)


@router.get("/privacy")
async def privacy_redirect() -> RedirectResponse:
    return RedirectResponse("/legal/privacy", status_code=302)


@router.get("/paysupport", response_class=HTMLResponse)
async def paysupport_page(request: Request, settings: Settings = Depends(get_settings)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "paysupport.html",
        {
            "title": "Поддержка по оплате",
            "subtitle": f"Актуально на {date.today().isoformat()}",
            "app_base_url": settings.app_base_url.rstrip("/"),
            "published": PUBLISHED,
        },
    )
