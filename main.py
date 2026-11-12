"""Bothost-compatible entry.

Bothost domain mode injects http_wrapper.py as PID1 on $PORT and only serves
GET /health, while spawning `python main.py` as a child. Killing PID1 crash-loops
the container. Instead we bind FastAPI on PORT+1 and point Bothost Traefik at that
port via update_domain (archive bots can retarget without rebuild).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time


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


def _pip_install(*packages: str) -> None:
    print(f"pip install {' '.join(packages)}", flush=True)
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--no-cache-dir", *packages]
    )


def _ensure_sqlite_driver() -> None:
    try:
        import aiosqlite  # noqa: F401

        return
    except ImportError:
        pass
    try:
        _pip_install("aiosqlite==0.20.0")
    except Exception as exc:  # noqa: BLE001
        print(f"WARN pip aiosqlite failed: {exc}", flush=True)
    import aiosqlite  # noqa: F401


def _run_migrations() -> None:
    print("Running Alembic migrations...", flush=True)
    env = os.environ.copy()
    root = os.path.dirname(os.path.abspath(__file__))
    vendor = os.path.join(root, "vendor")
    path_parts = [root, vendor]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        [p for p in path_parts + existing.split(os.pathsep) if p]
    )
    try:
        subprocess.check_call(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            env=env,
            cwd=root,
        )
    except subprocess.CalledProcessError as exc:
        print(f"WARN alembic failed ({exc}); falling back to metadata.create_all", flush=True)
        import asyncio

        async def _create() -> None:
            from app.core.db import Base, engine

            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(_create())


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

    data: dict[str, str] = {"url": url}
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


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _cmdline(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            return fh.read().replace(b"\x00", b" ").decode(errors="ignore")
    except OSError:
        return ""


def _detect_bothost_wrapper(platform_port: int) -> bool:
    ppid = os.getppid()
    cmd = _cmdline(ppid)
    if "http_wrapper" in cmd:
        return True
    if os.environ.get("DOMAIN") and _port_open(platform_port) and ppid > 1:
        return True
    return False


def _choose_listen_port() -> int:
    platform_port = int(os.environ.get("PORT", "8080"))
    override = (os.environ.get("APP_BIND_PORT") or "").strip()
    if override:
        return int(override)
    if _detect_bothost_wrapper(platform_port):
        # Keep wrapper on PLATFORM port; serve real app beside it.
        app_port = int(os.environ.get("BOTHOST_APP_PORT", str(platform_port + 1)))
        print(
            f"Bothost wrapper detected on {platform_port}; binding app to {app_port}",
            flush=True,
        )
        return app_port
    return platform_port


_prepare_runtime()
_ROOT = os.path.dirname(os.path.abspath(__file__))
_VENDOR = os.path.join(_ROOT, "vendor")
for _p in (_ROOT, _VENDOR):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
_existing = os.environ.get("PYTHONPATH", "")
_parts = [p for p in [_ROOT, _VENDOR, *_existing.split(os.pathsep)] if p]
os.environ["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(_parts))
_ensure_sqlite_driver()
from app.main import app  # noqa: E402  pylint: disable=wrong-import-position


def run() -> None:
    _run_migrations()
    port = _choose_listen_port()
    # Give Traefik a moment after deploy; webhook set against public domain.
    time.sleep(1)
    _set_telegram_webhook()
    print(f"Starting uvicorn main:app on 0.0.0.0:{port}", flush=True)
    print(
        f"BOTHOST_TRAFFIC_PORT={port} "
        "(set Bothost internal_port to this value if domain still hits wrapper)",
        flush=True,
    )
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
