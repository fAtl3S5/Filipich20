from __future__ import annotations

from fastapi import Header, HTTPException

from app.core.config import Settings, get_settings
from app.payments.yookassa import FakeYooKassaClient, HttpYooKassaClient, YooKassaClient

_yookassa_client: YooKassaClient | None = None


def get_yookassa() -> YooKassaClient:
    global _yookassa_client
    if _yookassa_client is None:
        settings = get_settings()
        if settings.yookassa_shop_id and settings.yookassa_secret_key:
            _yookassa_client = HttpYooKassaClient(settings)
        else:
            _yookassa_client = FakeYooKassaClient()
    return _yookassa_client


def set_yookassa(client: YooKassaClient) -> None:
    global _yookassa_client
    _yookassa_client = client


def require_admin_web(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    token = x_admin_token
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    if not token or token != settings.admin_web_token:
        raise HTTPException(status_code=401, detail="Unauthorized")
