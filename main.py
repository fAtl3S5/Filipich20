"""Bothost entry module.

Importing FastAPI `app` at module level helps Bothost detect an HTTP app and
avoid injecting the stub http_wrapper that only serves GET /health.
"""

from __future__ import annotations

import os
import subprocess
import sys


def _prepare_runtime() -> None:
    data_dir = os.environ.get("DATA_DIR", "/app/data")
    os.makedirs(data_dir, exist_ok=True)
    db_url = (os.environ.get("DATABASE_URL") or "").strip()
    if not db_url or db_url == "sqlite-bothost":
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{data_dir}/filippych.db"

    domain = (os.environ.get("DOMAIN") or "").strip()
    if domain:
        base = os.environ.get("APP_BASE_URL", "")
        if not base or "127.0.0.1" in base or "localhost" in base:
            os.environ["APP_BASE_URL"] = f"https://{domain.rstrip('/')}"
        ret = os.environ.get("YOOKASSA_RETURN_URL", "")
        if not ret or "127.0.0.1" in ret or "localhost" in ret:
            os.environ["YOOKASSA_RETURN_URL"] = (
                f"{os.environ['APP_BASE_URL'].rstrip('/')}/checkout/return"
            )


def _ensure_sqlite_driver() -> None:
    try:
        import aiosqlite  # noqa: F401
        return
    except ImportError:
        pass
    print("Installing aiosqlite into user site...", flush=True)
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--user",
            "--no-cache-dir",
            "aiosqlite==0.20.0",
        ]
    )


def _run_migrations() -> None:
    _ensure_sqlite_driver()
    print("Running Alembic migrations...", flush=True)
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"])


def _set_telegram_webhook() -> None:
    if os.environ.get("SET_TELEGRAM_WEBHOOK", "true").lower() not in {"1", "true", "yes"}:
        return
    token = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or ""
    base = (os.environ.get("APP_BASE_URL") or "").rstrip("/")
    if not token or not base:
        return
    path = os.environ.get("TELEGRAM_WEBHOOK_PATH", "/webhook")
    url = f"{base}{path}"
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    import urllib.parse
    import urllib.request

    data = {"url": url}
    if secret:
        data["secret_token"] = secret
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/setWebhook",
        data=body,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            print(f"setWebhook -> {resp.status} url={url}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"WARN setWebhook failed: {exc}", flush=True)


_prepare_runtime()

# Expose ASGI app for `uvicorn main:app` / Bothost HTTP detection.
from app.main import app  # noqa: E402  pylint: disable=wrong-import-position


def run() -> None:
    _run_migrations()
    _set_telegram_webhook()
    port = os.environ.get("PORT", "8080")
    print(f"Starting uvicorn main:app on 0.0.0.0:{port}", flush=True)
    os.execvp(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ],
    )


if __name__ == "__main__":
    run()
