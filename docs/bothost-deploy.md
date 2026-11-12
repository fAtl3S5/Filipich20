# Деплой на Bothost (bothost.ru)

Пошаговая инструкция для «Филипп ещё расскажет»: Telegram-бот + FastAPI + durable jobs.

Официальные доки: [быстрый старт](https://bothost.ru/docs/getting-started), [Dockerfile](https://bothost.ru/docs/custom-dockerfile), [домены/webhook](https://bothost.ru/docs/web-apps-domains), [env](https://bothost.ru/docs/environment-variables), [Git access](https://bothost.ru/docs/git-repository-access).

## Статус (актуально)

| Пункт | Состояние |
|---|---|
| **Live domain** | ✅ **https://bot-1794481994-6734-gleb23451245.bothost.tech** |
| Health | ✅ `/health` и `/healthz` → `db:true`, `production_ready:true` |
| Webhook | ✅ `POST /webhook` (секрет в панели); Telegram `setWebhook` уже вызывается при старте |
| Bot id | `bot_1794481994_6734_gleb23451245` |
| Deploy mode | archive (`filipich20-v8.zip`), не Git |
| GitHub `Filipich20` | ❌ PAT без Contents:write — репо пустое; код на agent branch |
| `ADMIN_IDS` | ✅ `475444567` |
| `CHANNEL_ID` | ✅ `-1004373038215` |
| `DISCUSSION_GROUP_ID` | ✅ `-1004381561059` |
| ЮKасса | ⏸ `ENABLE_WEB_YOOKASSA=false` |
| Stars | ✅ тест: `1/2/3/5` XTR на 1/3/6/12 мес (`ENABLE_STARS=true`) |

## Важно про домен Bothost

При включённом домене платформа всё равно поднимает stub `http_wrapper.py` на `$PORT` (только `GET /health`). Наш `main.py` детектит wrapper и слушает **`BOTHOST_APP_PORT` (по умолчанию PORT+1 = 8081)**. Traefik `internal_port` должен быть **8081**, при этом в env оставьте `PORT=8080` для wrapper. После смены порта для archive-бота нужно **снова залить архив**, иначе маршрут на ноде может не обновиться.

Нельзя kill’ить PID1 wrapper — контейнер уходит в crash-loop.

## Env в панели (без секретов в Git)

```text
APP_ENV=production
ADMIN_IDS=475444567
CHANNEL_ID=-1004373038215
DISCUSSION_GROUP_ID=-1004381561059
ENABLE_BOT_INITIATED_YOOKASSA=false
ENABLE_WEB_YOOKASSA=false
ENABLE_STARS=true
STARS_PRICE_1M=1
STARS_PRICE_3M=2
STARS_PRICE_6M=3
STARS_PRICE_12M=5
SET_TELEGRAM_WEBHOOK=true
TELEGRAM_WEBHOOK_PATH=/webhook
DATABASE_URL=sqlite-bothost
DATA_DIR=/app/data
PORT=8080
BOTHOST_APP_PORT=8081
SECRET_KEY=<сгенерировать>
TELEGRAM_WEBHOOK_SECRET=<сгенерировать>
ADMIN_WEB_TOKEN=<сгенерировать>
BOT_TOKEN=<из BotFather, только панель>
```

Domain settings: enabled, internal port **8081**.

## Redeploy из архива

1. Собрать zip из репо (включая `main.py`, `aiosqlite/`, `vendor/aiosqlite/`).
2. `POST /api/deploy-archive.php` с `bot_id` + `archive`.
3. Проверить `https://<domain>/health` — в JSON должны быть поля `db` и `env` (не голый `{"status":"ok"}` от wrapper).

## GitHub (когда будет write-PAT)

```bash
git push github HEAD:main
```

Затем можно переключить бота с archive на Git URL `https://github.com/fAtl3S5/Filipich20.git`, branch `main`.

Секреты (`BOT_TOKEN`, PAT, ЮKасса) — только панель / local secrets store, никогда в Git.
