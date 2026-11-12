# Деплой на Bothost (bothost.ru)

Пошаговая инструкция для «Филипп ещё расскажет»: Telegram-бот + FastAPI + durable jobs.

Официальные доки: [быстрый старт](https://bothost.ru/docs/getting-started), [Dockerfile](https://bothost.ru/docs/custom-dockerfile), [домены/webhook](https://bothost.ru/docs/web-apps-domains), [env](https://bothost.ru/docs/environment-variables), [Git access](https://bothost.ru/docs/git-repository-access).

## Статус (актуально)

| Пункт | Состояние |
|---|---|
| Код на GitHub | ✅ `https://github.com/fAtl3S5/Filipich20` (ветка `main` + `cursor/filippych-subscription-5307`) |
| `ADMIN_IDS` | ✅ `475444567` |
| `CHANNEL_ID` | ✅ `-1004373038215` |
| `DISCUSSION_GROUP_ID` | ✅ `-1004381561059` |
| Бот admin канала/группы | ✅ по словам владельца |
| ЮKасса | ⏸ пропуск: `ENABLE_WEB_YOOKASSA=false` |
| Bothost login / API key агента | ❌ **нет в store** — деплой в панель Bothost из агента невозможен без email/password или API-токена владельца |
| `BOT_TOKEN` / `SECRET_KEY` в панели | ⏳ ввести владельцу (не в Git) |

**Координатору нужно от владельца:** логин/пароль Bothost **или** иной способ входа (сессия/API), плюс `BOT_TOKEN` в панели (если ещё не сохранён там). Без этого агент не может «зайти сам».

---

## Feasibility (кратко)

Bothost = **один контейнер** (FastAPI + webhook + in-process jobs + HTTPS). Postgres one-click в доках бота нет → внешний Postgres или SQLite `/app/data`. Нужен платный тариф с доменом/env.

---

## Точные шаги в панели Bothost (владелец / когда дадут доступ)

1. Открыть [создать бота](https://bothost.ru/create-bot.php).
2. Заполнить:
   - **Git URL:** `https://github.com/fAtl3S5/Filipich20.git`
   - **Ветка:** `main`
   - **Платформа:** Telegram
   - **Bot Token:** токен @BotFather (только в панели)
3. Дополнительно:
   - ✅ **Использовать собственный Dockerfile**
   - ✅ **Использовать домен** (webhook/HTTPS)
   - **Внутренний порт:** `8080`
4. Если репозиторий приватный — [подключить доступ](https://bothost.ru/docs/git-repository-access): HTTPS, username `x-access-token`, PAT **read-only** (не коммитить).
5. Env в панели (скопировать):

```text
APP_ENV=production
ADMIN_IDS=475444567
CHANNEL_ID=-1004373038215
DISCUSSION_GROUP_ID=-1004381561059
ENABLE_BOT_INITIATED_YOOKASSA=false
ENABLE_WEB_YOOKASSA=false
ENABLE_STARS=true
SET_TELEGRAM_WEBHOOK=true
TELEGRAM_WEBHOOK_PATH=/webhook
DATABASE_URL=sqlite-bothost
DATA_DIR=/app/data
SECRET_KEY=<сгенерировать>
TELEGRAM_WEBHOOK_SECRET=<сгенерировать>
ADMIN_WEB_TOKEN=<сгенерировать>
```

Позже: внешний `DATABASE_URL=postgresql+asyncpg://...`, `STARS_PRICE_*` или `ENABLE_STARS=false`, ЮKасса когда будет готова.

6. Создать / **Обновить из Git** → логи сборки/работы.
7. Проверить: `https://<DOMAIN>/health`, `/start` боту, `getWebhookInfo`.

---

## Что уже в репо

- Bothost `Dockerfile` + `scripts/bothost_start.sh`
- `/health`, `/webhook`
- `.env.example` с заполненными несекретными ID и `ENABLE_WEB_YOOKASSA=false`

Секреты (`BOT_TOKEN`, PAT, ЮKасса) — **только панель / local secrets**, никогда в Git.
