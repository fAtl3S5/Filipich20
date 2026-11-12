from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any


def hash_token(raw: str, *, pepper: str) -> str:
    return hashlib.sha256(f"{pepper}:{raw}".encode()).hexdigest()


def generate_activation_token() -> str:
    return secrets.token_urlsafe(32)


def verify_telegram_login(
    data: dict[str, Any],
    *,
    bot_token: str,
    max_age_sec: int,
    now_ts: int,
) -> bool:
    """Verify Telegram Login Widget payload per official docs."""
    check_hash = data.get("hash")
    if not check_hash:
        return False
    auth_date = int(data.get("auth_date", 0))
    if now_ts - auth_date > max_age_sec:
        return False
    pairs = []
    for key in sorted(k for k in data.keys() if k != "hash"):
        pairs.append(f"{key}={data[key]}")
    data_check_string = "\n".join(pairs)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated, str(check_hash))


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
