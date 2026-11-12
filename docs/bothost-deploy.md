# Деплой на Bothost (bothost.ru)

Пошаговая инструкция для «Филипп ещё расскажет»: Telegram-бот + FastAPI (веб-ЮKасса) + durable jobs.

Официальные доки Bothost: [быстрый старт](https://bothost.ru/docs/getting-started), [кастомный Dockerfile](https://bothost.ru/docs/custom-dockerfile), [домены/webhook](https://bothost.ru/docs/web-apps-domains), [env](https://bothost.ru/docs/environment-variables), [хранение БД](https://bothost.ru/docs/database-storage).

## Краткий вердикт (feasibility)

| Нужно продукту | Bothost |
|---|---|
| Один контейнер с FastAPI + бот (webhook) + HTTPS-домен | **Да** (кастомный Dockerfile + «Использовать домен») |
| Durable jobs | **Да** — jobs крутятся **внутри** API-процесса (отдельный worker-контейнер Bothost не даёт) |
| Публичный `/checkout` для ЮKассы | **Да** (тот же HTTPS-домен) |
| Встроенный managed PostgreSQL «из коробки» для бота | **Нет явного one-click Postgres в доках бота** |
| Персистентный диск | **Да** — том `/app/data` (обычно SQLite) |
| Несколько процессов / docker-compose services | **Нет** — один контейнер на бота |

**Рекомендуемая схема:** Bothost = бот + API + webhook + checkout; **Postgres — внешний** (Neon / Supabase / Railway / Selectel / Yandex Managed PostgreSQL и т.п.) через `DATABASE_URL`.

**Аварийный MVP на Bothost без внешнего Postgres:** `DATABASE_URL=sqlite-bothost` → файл `/app/data/filippych.db`. Подходит только для старта/малых нагрузок (один писатель). Для денег и параллельных оплат лучше Postgres.

**Тариф:** для env-переменных, домена и webhook нужен **платный** план Bothost (Basic/Pro). На free FAQ указывает long polling без webhook — для этого продукта **недостаточно**.

Реальный production-деплой **нельзя завершить без** логина владельца в Bothost и его секретов. Ниже — всё, что подготовлено в репо, и точные клики владельца.

---

## Что уже подготовлено в репозитории

- `Dockerfile` — Bothost-совместимый (`WORKDIR /usr/src/app`, данные в `/app/data`, слушает `0.0.0.0:$PORT`)
- `scripts/bothost_start.sh` — миграции Alembic → `setWebhook` → uvicorn
- Эндпоинты: `GET /health`, `POST /webhook` (алиасы к `/healthz` и `/webhooks/telegram`)
- In-process job worker (отдельный сервис на Bothost не нужен)
- `.env.example` — плейсхолдеры, без секретов

---

## Чеклист: что владелец должен предоставить

### Обязательно

1. **Аккаунт Bothost** + оплаченный тариф с доменом/env (Basic+)
2. **Публичный Git-репозиторий** (или доступ Bothost к приватному) с веткой деплоя
3. `BOT_TOKEN` от @BotFather
4. Числовые `CHANNEL_ID` и `DISCUSSION_GROUP_ID` (бот — админ обоих чатов: invite, ban, delete messages, manage join requests)
5. **Закрыть вручную** все старые открытые/незащищённые инвайты канала и группы
6. `ADMIN_IDS` — Telegram user id владельца/админов
7. `SECRET_KEY`, `TELEGRAM_WEBHOOK_SECRET`, `ADMIN_WEB_TOKEN` — длинные случайные строки
8. ЮKасса: `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` (+ webhook магазина на `https://<DOMAIN>/webhooks/yookassa`)
9. База: **внешний** `DATABASE_URL` (`postgresql+asyncpg://...`) *или* осознанный SQLite fallback

### Желательно / по сценарию

- `STARS_PRICE_1M`…`12M` или `ENABLE_STARS=false`
- `SUPPORT_URL` / `TERMS_URL` / `PAYSUPPORT_URL`
- `TELEGRAM_LOGIN_BOT_USERNAME` (иначе activation token после веб-оплаты)
- `BAN_ALLOWLIST`
- Проверка reading-ограничения discussion group (см. `docs/discussion-group-limitation.md`)

Секреты вводить **только в панели Bothost**, не в Git.

---

## Пошагово в панели Bothost

### 1) Репозиторий

1. Создайте/подключите GitHub/GitLab репозиторий с этим кодом.
2. Убедитесь, что в корне есть `Dockerfile`, `requirements.txt`, `scripts/bothost_start.sh`.
3. Задеплойте нужную ветку (например `main` после merge, или feature-ветку для пробы).

### 2) Создать бота

1. Откройте [bothost.ru/create-bot.php](https://bothost.ru/create-bot.php) (или «Создать бота» в кабинете).
2. Заполните:
   - **Название** — любое (например `filippych-sub`)
   - **Платформа** — Telegram
   - **Bot Token** — токен @BotFather (Bothost также прокинет `BOT_TOKEN` в env)
   - **Git URL** + **ветка**
3. **Дополнительные настройки** (обязательно):
   - ✅ **Использовать собственный Dockerfile**
   - ✅ **Использовать домен** / «веб-интерфейс / админку / webhook»
   - **Внутренний порт** = `8080` (должен совпадать с `PORT`; наш скрипт читает `PORT`, по умолчанию 8080)
   - **Главный файл** — можно оставить пустым: при своём Dockerfile важен `CMD` в Dockerfile
4. Нажмите **Создать бота** / дождитесь сборки. Смотрите **логи сборки** и **логи работы**.

### 3) Переменные окружения

В карточке бота → **Переменные окружения** → добавьте:

```text
APP_ENV=production
SECRET_KEY=<длинная-случайная>
ADMIN_WEB_TOKEN=<длинная-случайная>
TELEGRAM_WEBHOOK_SECRET=<длинная-случайная>
ADMIN_IDS=<ваш_telegram_id>
CHANNEL_ID=<число>
DISCUSSION_GROUP_ID=<число>
ENABLE_BOT_INITIATED_YOOKASSA=false
ENABLE_WEB_YOOKASSA=true
YOOKASSA_SHOP_ID=<shopId>
YOOKASSA_SECRET_KEY=<secret>
ENABLE_STARS=false
# или задайте STARS_PRICE_1M=... и т.д.
SET_TELEGRAM_WEBHOOK=true
TELEGRAM_WEBHOOK_PATH=/webhook
```

База (предпочтительно):

```text
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DBNAME
```

Либо SQLite на томе Bothost:

```text
DATABASE_URL=sqlite-bothost
DATA_DIR=/app/data
```

`DOMAIN` и `PORT` Bothost обычно выставляет сам. `APP_BASE_URL` и `YOOKASSA_RETURN_URL` подхватятся из `DOMAIN` скриптом/конфигом, если не заданы явно.

После сохранения env — **повторный деплой** («Обновить из Git» / redeploy), не только restart.

### 4) Проверки после деплоя

1. Откройте `https://<DOMAIN>/health` → `{"status":"ok",...}`
2. Откройте `https://<DOMAIN>/checkout` → страница тарифов
3. В браузере/логах проверьте webhook:
   - `https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
   - `url` = `https://<DOMAIN>/webhook`
4. Напишите боту `/start` в Telegram
5. В ЮKассе укажите HTTP-уведомления на `https://<DOMAIN>/webhooks/yookassa`

### 5) ЮKасса и Stars

- Веб-checkout: `https://<DOMAIN>/checkout`
- Не включайте `ENABLE_BOT_INITIATED_YOOKASSA` в production без compliance review
- Stars — только с ценами владельца в XTR

---

## Webhook vs polling на Bothost

| Режим | Когда |
|---|---|
| **Webhook (нужен этому продукту)** | Платный план + домен HTTPS + `POST /webhook` |
| Long polling | Free / без домена — **не подходит** для совместного FastAPI checkout + webhook ЮKассы в одном HTTPS |

Скрипт старта сам вызывает `setWebhook` на `APP_BASE_URL + TELEGRAM_WEBHOOK_PATH` (по умолчанию `/webhook`), если `SET_TELEGRAM_WEBHOOK=true`.

Отключить авто-set: `SET_TELEGRAM_WEBHOOK=false` и выставить webhook вручную.

---

## Почему не «полный» docker-compose на Bothost

Bothost запускает **один** контейнер бота. Сервисы `db` + `api` + `worker` из `docker-compose.yml` — для локальной/своей VPS разработки. На Bothost:

- API + jobs = один процесс uvicorn (jobs в asyncio)
- Postgres = снаружи (или SQLite в `/app/data`)

Отдельный `python -m app.worker_main` на Bothost **не** поднимается вторым сервисом той же кнопкой «создать бота» (можно завести второй «бот»-контейнер с тем же Git и командой worker — избыточно, если хватает in-process worker).

---

## Минимальный workable layout

```text
[Telegram] --webhook--> https://<bothost-domain>/webhook
[Browser]  --checkout-> https://<bothost-domain>/checkout --> YooKassa hosted
[YooKassa] --webhook--> https://<bothost-domain>/webhooks/yookassa
                |
                v
        Bothost container (FastAPI + aiogram + jobs)
                |
                v
     External PostgreSQL  (recommended)
        or /app/data/filippych.db (MVP only)
```

---

## Типовые поломки

- **502/504** — приложение не слушает `0.0.0.0`/`PORT`, или внутренний порт в панели ≠ 8080
- **Webhook 404** — в Telegram указан не `/webhook`
- **403 на Telegram webhook** — не совпал `TELEGRAM_WEBHOOK_SECRET`
- **Потеря SQLite** — база не в `/app/data`
- **Мало RAM (256MB)** — Starter тесен для FastAPI+SQLAlchemy; берите Basic+

---

## После успешного деплоя (владелец)

1. Закрыть старые инвайты канала/группы  
2. Прогнать тестовую оплату (ЮKасса test / Stars test env)  
3. Проверить join-request без подписки (должен decline)  
4. Проверить expire/renew на тестовом аккаунте  
5. Настроить backup внешней БД  
6. Не коммитить `.env` / токены
