#!/usr/bin/env bash
# Bothost entrypoint: migrations + single process (FastAPI + in-process durable jobs).
set -euo pipefail

export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# Bothost injects DOMAIN and PORT; prefer them when APP_BASE_URL is unset/default.
if [[ -n "${DOMAIN:-}" ]]; then
  if [[ -z "${APP_BASE_URL:-}" || "${APP_BASE_URL}" == "http://127.0.0.1:8741" ]]; then
    export APP_BASE_URL="https://${DOMAIN}"
  fi
  if [[ -z "${YOOKASSA_RETURN_URL:-}" || "${YOOKASSA_RETURN_URL}" == *"127.0.0.1"* ]]; then
    export YOOKASSA_RETURN_URL="${APP_BASE_URL}/checkout/return"
  fi
fi

# Optional SQLite on Bothost volume when DATABASE_URL is empty / sqlite-bothost.
DATA_DIR="${DATA_DIR:-/app/data}"
mkdir -p "${DATA_DIR}"
if [[ -z "${DATABASE_URL:-}" || "${DATABASE_URL}" == "sqlite-bothost" ]]; then
  export DATABASE_URL="sqlite+aiosqlite:///${DATA_DIR}/filippych.db"
  echo "Using SQLite at ${DATA_DIR}/filippych.db (Bothost volume). Prefer external Postgres for production."
fi

PORT="${PORT:-8080}"
echo "Running Alembic migrations..."
alembic upgrade head

if [[ "${SET_TELEGRAM_WEBHOOK:-true}" == "true" && -n "${BOT_TOKEN:-}" && -n "${APP_BASE_URL:-}" ]]; then
  SECRET="${TELEGRAM_WEBHOOK_SECRET:-}"
  # Prefer Bothost-friendly /webhook; also works with /webhooks/telegram
  WEBHOOK_PATH="${TELEGRAM_WEBHOOK_PATH:-/webhook}"
  WEBHOOK_URL="${APP_BASE_URL%/}${WEBHOOK_PATH}"
  echo "Setting Telegram webhook to ${WEBHOOK_URL}"
  if [[ -n "${SECRET}" ]]; then
    curl -fsS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
      -d "url=${WEBHOOK_URL}" \
      -d "secret_token=${SECRET}" \
      -d "allowed_updates=$(printf '%s' '["message","callback_query","pre_checkout_query","successful_payment","chat_join_request","chat_member","my_chat_member"]')" \
      || echo "WARN: setWebhook failed (check token/domain)"
  else
    curl -fsS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
      -d "url=${WEBHOOK_URL}" \
      || echo "WARN: setWebhook failed (check token/domain)"
  fi
fi

echo "Starting uvicorn on 0.0.0.0:${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
