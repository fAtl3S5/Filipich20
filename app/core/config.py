from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    app_base_url: str = "http://127.0.0.1:8741"
    secret_key: str = "dev-secret-change-me"
    admin_web_token: str = "dev-admin-token"

    bot_token: str = ""
    telegram_webhook_secret: str = "dev-webhook-secret"
    admin_ids: list[int] = Field(default_factory=list)
    channel_id: int | None = None
    discussion_group_id: int | None = None
    channel_invite_hint: str = ""
    discussion_invite_hint: str = ""
    ban_allowlist: list[int] = Field(default_factory=list)

    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_return_url: str = "http://127.0.0.1:8741/checkout/return"
    enable_bot_initiated_yookassa: bool = False
    enable_web_yookassa: bool = True

    stars_price_1m: int | None = None
    stars_price_3m: int | None = None
    stars_price_6m: int | None = None
    stars_price_12m: int | None = None
    enable_stars: bool = True

    telegram_login_bot_username: str = ""
    telegram_login_auth_date_max_age: int = 86400

    support_url: str = ""
    terms_url: str = ""
    paysupport_url: str = ""

    database_url: str = "postgresql+asyncpg://filippych:filippych@localhost:5432/filippych"

    display_timezone: str = "Asia/Novosibirsk"

    job_poll_interval_sec: int = 5
    expire_sweep_interval_sec: int = 60
    broadcast_rate_limit_per_sec: float = 25.0

    @field_validator("admin_ids", "ban_allowlist", mode="before")
    @classmethod
    def parse_id_list(cls, value: object) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [int(v) for v in value]
        if isinstance(value, int):
            return [value]
        text = str(value).strip()
        if not text:
            return []
        return [int(part.strip()) for part in text.split(",") if part.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}

    @property
    def stars_prices(self) -> dict[int, int]:
        mapping: dict[int, int] = {}
        for months, price in (
            (1, self.stars_price_1m),
            (3, self.stars_price_3m),
            (6, self.stars_price_6m),
            (12, self.stars_price_12m),
        ):
            if price is not None and price > 0:
                mapping[months] = int(price)
        return mapping

    def production_missing_env(self) -> list[str]:
        required = [
            "BOT_TOKEN",
            "SECRET_KEY",
            "ADMIN_IDS",
            "CHANNEL_ID",
            "DISCUSSION_GROUP_ID",
            "DATABASE_URL",
            "TELEGRAM_WEBHOOK_SECRET",
        ]
        missing: list[str] = []
        checks = {
            "BOT_TOKEN": self.bot_token,
            "SECRET_KEY": self.secret_key and self.secret_key != "dev-secret-change-me",
            "ADMIN_IDS": bool(self.admin_ids),
            "CHANNEL_ID": self.channel_id is not None,
            "DISCUSSION_GROUP_ID": self.discussion_group_id is not None,
            "DATABASE_URL": bool(self.database_url),
            "TELEGRAM_WEBHOOK_SECRET": (
                bool(self.telegram_webhook_secret)
                and self.telegram_webhook_secret != "dev-webhook-secret"
            ),
        }
        for key in required:
            if not checks[key]:
                missing.append(key)
        if self.enable_web_yookassa:
            if not self.yookassa_shop_id:
                missing.append("YOOKASSA_SHOP_ID")
            if not self.yookassa_secret_key:
                missing.append("YOOKASSA_SECRET_KEY")
        if self.enable_stars and not self.stars_prices:
            # Stars enabled without prices is allowed in local; warn in prod checklist.
            missing.append("STARS_PRICE_* (or disable ENABLE_STARS)")
        return missing


@lru_cache
def get_settings() -> Settings:
    return Settings()
