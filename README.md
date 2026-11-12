# Филипп ещё расскажет — платная подписка

Система разовой платной подписки на закрытый канал **«Филипп ещё расскажет»** и связанную группу комментариев.

Одна подписка = доступ к каналу **и** комментариям. Одна дата окончания. Отдельная «подписка на группу» не продаётся.

## Что внутри

- Telegram-бот (aiogram 3): оформление, статус, «Войти в канал», поддержка, админка, рассылки
- FastAPI: веб-checkout ЮKассы, webhooks, health, admin API
- PostgreSQL + SQLAlchemy + Alembic
- Durable jobs в БД (несколько workers без double-credit)
- Тесты критических сценариев с моками

## Два платёжных сценария (важно)

### 1) Telegram Stars (внутри Telegram)

По [правилам Telegram](https://core.telegram.org/bots/payments-stars) и [Bot Developer Terms](https://telegram.org/tos/bot-developers), **цифровой доступ внутри Telegram/бота/mini-app оплачивается только в Stars (`XTR`)**.

В боте доступен адаптер Stars. Цены XTR задаёт владелец (`STARS_PRICE_1M` и т.д.). Пока цены не заданы — тарифы Stars скрыты; веб-ЮKасса и доступ при этом работают.

Обязательные команды: `/terms`, `/support`, `/paysupport`.

### 2) ЮKасса на независимой веб-странице

Рублёвая оплата идёт через **отдельную страницу** `/checkout` (hosted checkout ЮKассы), **не** через Telegram Payments и **не** как «разрешённый» способ из бота в production.

`ENABLE_BOT_INITIATED_YOOKASSA=false` по умолчанию. В production не включайте инициацию ЮKассы из бота без проверки соответствия правилам магазинов приложений и Telegram.

Доступ после веб-оплаты привязывается через:

- Telegram Login Widget (проверенная подпись), **или**
- одноразовый activation token (`/start activate_<token>`), TTL, хранение hash, один заказ → один аккаунт.

`return_url` / «я оплатил» / браузер **не** активируют доступ. Только проверенный webhook → API ЮKассы → сверка суммы/валюты/заказа → атомарная запись.

## Тарифы (копейки)

| Срок | Сумма |
|------|-------|
| 1 мес | 99000 |
| 3 мес | 269000 |
| 6 мес | 499000 |
| 12 мес | 899000 |

Календарные месяцы (не 30 дней). Хранение UTC, отображение `Asia/Novosibirsk` с указанием пояса. Без автосписаний: «Разовая оплата. Без автоматических списаний».

## Быстрый старт

```bash
cp .env.example .env
# заполните BOT_TOKEN, ADMIN_IDS, CHANNEL_ID, DISCUSSION_GROUP_ID, YOOKASSA_*, SECRET_KEY

docker compose up --build
```

Сервисы: API `http://127.0.0.1:8741`, Postgres `55432`, worker.

Локально без Docker:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# поднимите Postgres и пропишите DATABASE_URL
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8741
# отдельно: python -m app.worker_main
```

Тесты:

```bash
pytest -q
```

## Как получить CHANNEL_ID / DISCUSSION_GROUP_ID

1. Добавьте бота **админом** в канал и в группу комментариев (права: invite users, ban users, delete messages, manage join requests).
2. Привяжите группу как discussion к каналу в настройках Telegram.
3. Напишите в канал/группу или сделайте join request; посмотрите `chat.id` через `getUpdates` или бота вроде `@userinfobot` / `@RawDataBot`.
4. Пропишите числовые id в `.env` (`CHANNEL_ID`, `DISCUSSION_GROUP_ID`).

Инвайты владельца (только подсказка, не открывайте незащищённые ссылки в production):

- Канал: `https://t.me/+ymhxwNravd9hMzUy`
- Группа: `https://t.me/+2MH4qJ7o8Mg1NmIy`

На старте **закройте вручную** все старые открытые инвайты. Бот не обещает отозвать чужие ссылки.

## Права бота и вход

После оплаты: активировать подписку → `unbanChatMember(only_if_banned=true)` в канале и группе → кнопка **«Войти в канал»** (invite с `creates_join_request=true`, без `member_limit`).

Join request: проверка `telegram_user_id` + активная подписка. Пересланная ссылка сама по себе доступ не даёт.

По окончании: ban в канале и группе. Повторная оплата снимает только бан за истечение. Manual ban за правила не снимается.

## Ограничение: чтение discussion group

Удаление сообщений и kick/ban ограничивают **публикацию** и членство. Стандартная связка channel → discussion **не гарантирует** запрет **чтения** треда комментариев через кнопку под постом канала, если клиент Telegram показывает тред без полноценного join.

До production:

1. Канал и группа — только private, без username и открытых инвайтов.
2. Проверить тестовым аккаунтом без подписки, виден ли тред после kick/ban.
3. Если чтение всё ещё возможно — не заявлять «полную защиту»; рассмотреть отключение discussion или отдельный закрытый чат только по join request.

Подробности: `DISCUSSION_READ_LIMITATION` в `app/services/access.py`.

## Деплой на Bothost

Платформа [Bothost](https://bothost.ru) подходит для **одного контейнера** (FastAPI + бот + in-process jobs + HTTPS-домен). Встроенного one-click PostgreSQL в доках бота нет — берите **внешний Postgres** (или временный SQLite на томе `/app/data`).

Пошаговая инструкция владельца: [`docs/bothost-deploy.md`](docs/bothost-deploy.md).

Кратко в панели Bothost:

1. Создать бота из Git, включить **свой Dockerfile** и **домен**
2. Внутренний порт `8080`
3. Прописать env из `.env.example` (секреты только в панели)
4. Проверить `https://<DOMAIN>/health` и `https://<DOMAIN>/checkout`
5. ЮKасса webhook → `/webhooks/yookassa`; Telegram → `/webhook`

## Webhooks

- ЮKасса: `POST /webhooks/yookassa` — тело не доверяем; платеж перечитывается через API.
- Telegram: `POST /webhook` (Bothost-алиас) или `POST /webhooks/telegram` + заголовок `X-Telegram-Bot-Api-Secret-Token`.

## Админка

В боте: `/admin`, `/grant`, `/revoke`, `/find`, `/broadcast` — только `ADMIN_IDS`.

HTTP: `/admin/api/stats`, `/admin/api/users/{telegram_user_id}` с `Authorization: Bearer $ADMIN_WEB_TOKEN`.

Финансы: confirmed / refunds / unpaid раздельно. Ручные grant не считаются выручкой.

## Backup / restore

```bash
./scripts/backup.sh ./backups
./scripts/restore.sh ./backups/filippych-....sql.gz
```

## Production checklist (заполнить владельцу)

- [ ] `BOT_TOKEN`, `SECRET_KEY`, `TELEGRAM_WEBHOOK_SECRET`, `ADMIN_WEB_TOKEN`
- [ ] `ADMIN_IDS`
- [ ] `CHANNEL_ID`, `DISCUSSION_GROUP_ID` (бот — админ обоих чатов)
- [ ] Закрыть старые незащищённые инвайты
- [ ] `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY`, `YOOKASSA_RETURN_URL`, HTTPS `APP_BASE_URL`
- [ ] Настроить webhook ЮKассы на `/webhooks/yookassa`
- [ ] Настроить Telegram webhook + `secret_token`
- [ ] `ENABLE_BOT_INITIATED_YOOKASSA=false` (оставьте так, пока нет legal/compliance review)
- [ ] Задать `STARS_PRICE_*` или `ENABLE_STARS=false`
- [ ] `SUPPORT_URL` / `TERMS_URL` / `PAYSUPPORT_URL` (для Stars обязательны понятные /terms /support /paysupport)
- [ ] `TELEGRAM_LOGIN_BOT_USERNAME` для Login Widget (опционально, иначе activation token)
- [ ] Проверить ограничение чтения discussion (см. выше)
- [ ] Алерты админам на failed jobs (`admin_alert`)
- [ ] Регулярный backup Postgres

Локальные секреты для smoke **никогда не коммитить**. Пример — `.env.example`.
