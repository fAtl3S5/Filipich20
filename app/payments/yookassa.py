from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

YOOKASSA_API = "https://api.yookassa.ru/v3"


class YooKassaClient(Protocol):
    async def create_payment(
        self,
        *,
        amount_kopecks: int,
        currency: str,
        description: str,
        idempotence_key: str,
        return_url: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def get_payment(self, payment_id: str) -> dict[str, Any]: ...


class HttpYooKassaClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _auth(self) -> tuple[str, str]:
        return self.settings.yookassa_shop_id, self.settings.yookassa_secret_key

    async def create_payment(
        self,
        *,
        amount_kopecks: int,
        currency: str,
        description: str,
        idempotence_key: str,
        return_url: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        value = f"{amount_kopecks // 100}.{amount_kopecks % 100:02d}"
        payload = {
            "amount": {"value": value, "currency": currency},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "description": description,
            "metadata": metadata,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{YOOKASSA_API}/payments",
                json=payload,
                auth=self._auth(),
                headers={"Idempotence-Key": idempotence_key},
            )
            response.raise_for_status()
            return response.json()

    async def get_payment(self, payment_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{YOOKASSA_API}/payments/{payment_id}",
                auth=self._auth(),
            )
            response.raise_for_status()
            return response.json()


class FakeYooKassaClient:
    def __init__(self) -> None:
        self.payments: dict[str, dict[str, Any]] = {}
        self.created: list[dict[str, Any]] = []

    async def create_payment(
        self,
        *,
        amount_kopecks: int,
        currency: str,
        description: str,
        idempotence_key: str,
        return_url: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        for existing in self.payments.values():
            if existing.get("_idempotence_key") == idempotence_key:
                return existing
        payment_id = f"yk_{len(self.payments) + 1}"
        value = f"{amount_kopecks // 100}.{amount_kopecks % 100:02d}"
        data = {
            "id": payment_id,
            "status": "pending",
            "paid": False,
            "amount": {"value": value, "currency": currency},
            "confirmation": {
                "type": "redirect",
                "confirmation_url": f"https://yookassa.test/confirm/{payment_id}",
            },
            "metadata": metadata,
            "description": description,
            "_idempotence_key": idempotence_key,
            "_return_url": return_url,
        }
        self.payments[payment_id] = data
        self.created.append(data)
        return data

    async def get_payment(self, payment_id: str) -> dict[str, Any]:
        if payment_id not in self.payments:
            raise KeyError(payment_id)
        return self.payments[payment_id]

    def mark_succeeded(self, payment_id: str) -> dict[str, Any]:
        data = self.payments[payment_id]
        data["status"] = "succeeded"
        data["paid"] = True
        return data

    def mark_canceled(self, payment_id: str) -> dict[str, Any]:
        data = self.payments[payment_id]
        data["status"] = "canceled"
        data["paid"] = False
        return data


def parse_amount_to_kopecks(amount: dict[str, Any]) -> int:
    value = str(amount["value"])
    rub, _, kop = value.partition(".")
    kop = (kop + "00")[:2]
    return int(rub) * 100 + int(kop)
