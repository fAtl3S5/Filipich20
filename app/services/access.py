from __future__ import annotations

import logging
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.timeutil import ensure_utc, utcnow
from app.models.entities import (
    AccessAction,
    AccessActionType,
    AccessTarget,
    User,
)
from app.services.users import get_user_by_telegram_id, is_subscription_active

logger = logging.getLogger(__name__)


class TelegramAccessClient(Protocol):
    async def unban(self, chat_id: int, user_id: int, *, only_if_banned: bool = True) -> bool: ...

    async def ban(self, chat_id: int, user_id: int) -> bool: ...

    async def approve_join_request(self, chat_id: int, user_id: int) -> bool: ...

    async def decline_join_request(self, chat_id: int, user_id: int) -> bool: ...

    async def create_chat_invite_link(
        self, chat_id: int, *, creates_join_request: bool = True, name: str | None = None
    ) -> str: ...

    async def delete_message(self, chat_id: int, message_id: int) -> bool: ...

    async def get_chat_member_status(self, chat_id: int, user_id: int) -> str: ...


class NullTelegramAccessClient:
    """In-memory fake for tests."""

    def __init__(self) -> None:
        self.actions: list[tuple] = []
        self.invite_links: dict[int, str] = {}
        self.banned: set[tuple[int, int]] = set()
        self.members: set[tuple[int, int]] = set()

    async def unban(self, chat_id: int, user_id: int, *, only_if_banned: bool = True) -> bool:
        self.actions.append(("unban", chat_id, user_id, only_if_banned))
        self.banned.discard((chat_id, user_id))
        return True

    async def ban(self, chat_id: int, user_id: int) -> bool:
        self.actions.append(("ban", chat_id, user_id))
        self.banned.add((chat_id, user_id))
        self.members.discard((chat_id, user_id))
        return True

    async def approve_join_request(self, chat_id: int, user_id: int) -> bool:
        self.actions.append(("approve", chat_id, user_id))
        self.members.add((chat_id, user_id))
        return True

    async def decline_join_request(self, chat_id: int, user_id: int) -> bool:
        self.actions.append(("decline", chat_id, user_id))
        return True

    async def create_chat_invite_link(
        self, chat_id: int, *, creates_join_request: bool = True, name: str | None = None
    ) -> str:
        link = f"https://t.me/+test-{chat_id}-{user_id if False else 'invite'}"
        # deterministic per chat
        link = self.invite_links.get(chat_id) or f"https://t.me/+join-{chat_id}"
        self.invite_links[chat_id] = link
        self.actions.append(("invite", chat_id, creates_join_request, name))
        return link

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        self.actions.append(("delete_message", chat_id, message_id))
        return True

    async def get_chat_member_status(self, chat_id: int, user_id: int) -> str:
        if (chat_id, user_id) in self.banned:
            return "kicked"
        if (chat_id, user_id) in self.members:
            return "member"
        return "left"


def _protected_ids(settings: Settings) -> set[int]:
    return set(settings.admin_ids) | set(settings.ban_allowlist)


async def _log_action(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    target: AccessTarget,
    action: AccessActionType,
    user_id: int | None = None,
    success: bool = True,
    detail: str | None = None,
) -> None:
    session.add(
        AccessAction(
            user_id=user_id,
            telegram_user_id=telegram_user_id,
            target=target,
            action=action,
            success=success,
            detail=detail,
        )
    )


async def provision_access(
    session: AsyncSession,
    client: TelegramAccessClient,
    telegram_user_id: int,
    *,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    user = await get_user_by_telegram_id(session, telegram_user_id)
    if user is None or not is_subscription_active(user):
        return {"ok": False, "reason": "inactive"}

    results: dict[str, object] = {"ok": True}
    for target, chat_id, manual_flag in (
        (AccessTarget.channel, settings.channel_id, user.manual_ban_channel),
        (AccessTarget.discussion, settings.discussion_group_id, user.manual_ban_discussion),
    ):
        if chat_id is None:
            results[target.value] = "chat_id_missing"
            continue
        if manual_flag:
            results[target.value] = "manual_ban_preserved"
            continue
        try:
            await client.unban(chat_id, telegram_user_id, only_if_banned=True)
            await _log_action(
                session,
                telegram_user_id=telegram_user_id,
                user_id=user.id,
                target=target,
                action=AccessActionType.unban,
            )
            if target == AccessTarget.channel:
                user.channel_access_state = "allowed"
            else:
                user.discussion_access_state = "allowed"
            results[target.value] = "unbanned"
        except Exception as exc:  # noqa: BLE001
            logger.exception("provision failed")
            await _log_action(
                session,
                telegram_user_id=telegram_user_id,
                user_id=user.id,
                target=target,
                action=AccessActionType.unban,
                success=False,
                detail=str(exc),
            )
            results[target.value] = f"error:{exc}"
            results["ok"] = False
    await session.flush()
    return results


async def create_channel_invite(
    session: AsyncSession,
    client: TelegramAccessClient,
    telegram_user_id: int,
    *,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    user = await get_user_by_telegram_id(session, telegram_user_id)
    if user is None or not is_subscription_active(user):
        raise PermissionError("Нет активной подписки")
    if settings.channel_id is None:
        raise RuntimeError("CHANNEL_ID не задан")
    link = await client.create_chat_invite_link(
        settings.channel_id,
        creates_join_request=True,
        name=f"u{telegram_user_id}",
    )
    await _log_action(
        session,
        telegram_user_id=telegram_user_id,
        user_id=user.id,
        target=AccessTarget.channel,
        action=AccessActionType.invite_sent,
        detail=link.split("/")[-1][:32],
    )
    await session.flush()
    return link


async def handle_join_request(
    session: AsyncSession,
    client: TelegramAccessClient,
    *,
    chat_id: int,
    telegram_user_id: int,
    settings: Settings | None = None,
) -> bool:
    settings = settings or get_settings()
    target = _target_for_chat(chat_id, settings)
    if target is None:
        return False
    user = await get_user_by_telegram_id(session, telegram_user_id)
    active = user is not None and is_subscription_active(user)
    if active and user is not None:
        manual = (
            user.manual_ban_channel
            if target == AccessTarget.channel
            else user.manual_ban_discussion
        )
        if manual:
            await client.decline_join_request(chat_id, telegram_user_id)
            await _log_action(
                session,
                telegram_user_id=telegram_user_id,
                user_id=user.id,
                target=target,
                action=AccessActionType.decline_join,
                detail="manual_ban",
            )
            await session.flush()
            return False
        await client.approve_join_request(chat_id, telegram_user_id)
        await _log_action(
            session,
            telegram_user_id=telegram_user_id,
            user_id=user.id,
            target=target,
            action=AccessActionType.approve_join,
        )
        await session.flush()
        return True

    await client.decline_join_request(chat_id, telegram_user_id)
    await _log_action(
        session,
        telegram_user_id=telegram_user_id,
        user_id=user.id if user else None,
        target=target,
        action=AccessActionType.decline_join,
        detail="no_active_subscription",
    )
    await session.flush()
    return False


async def expire_access(
    session: AsyncSession,
    client: TelegramAccessClient,
    telegram_user_id: int,
    *,
    expected_ends_at: str | None = None,
    settings: Settings | None = None,
) -> dict:
    """Ban expired user from channel + discussion. Race-safe vs renewals."""
    settings = settings or get_settings()
    if telegram_user_id in _protected_ids(settings):
        return {"ok": False, "reason": "protected"}

    user = await get_user_by_telegram_id(session, telegram_user_id)
    if user is None:
        return {"ok": False, "reason": "unknown_user"}

    if is_subscription_active(user):
        # Renewed — restore instead of ban
        return await provision_access(session, client, telegram_user_id, settings=settings)

    if expected_ends_at and user.subscription_ends_at:
        if ensure_utc(user.subscription_ends_at).isoformat() != expected_ends_at:
            # ends_at changed (renewal) — do not ban
            if is_subscription_active(user):
                return await provision_access(session, client, telegram_user_id, settings=settings)
            # Different expired version — still expire if currently inactive
            pass

    results: dict[str, object] = {"ok": True}
    for target, chat_id in (
        (AccessTarget.channel, settings.channel_id),
        (AccessTarget.discussion, settings.discussion_group_id),
    ):
        if chat_id is None:
            results[target.value] = "chat_id_missing"
            continue
        try:
            await client.ban(chat_id, telegram_user_id)
            await _log_action(
                session,
                telegram_user_id=telegram_user_id,
                user_id=user.id,
                target=target,
                action=AccessActionType.ban_expire,
            )
            if target == AccessTarget.channel:
                user.channel_access_state = "expired_banned"
            else:
                user.discussion_access_state = "expired_banned"
            results[target.value] = "banned"
        except Exception as exc:  # noqa: BLE001
            await _log_action(
                session,
                telegram_user_id=telegram_user_id,
                user_id=user.id,
                target=target,
                action=AccessActionType.ban_expire,
                success=False,
                detail=str(exc),
            )
            results[target.value] = f"error:{exc}"
            results["ok"] = False
    await session.flush()
    return results


async def enforce_discussion_message(
    session: AsyncSession,
    client: TelegramAccessClient,
    *,
    chat_id: int,
    telegram_user_id: int,
    message_id: int,
    is_automatic_forward: bool = False,
    is_admin: bool = False,
    settings: Settings | None = None,
) -> bool:
    """Return True if message is allowed to stay."""
    settings = settings or get_settings()
    if settings.discussion_group_id is None or chat_id != settings.discussion_group_id:
        return True
    if is_automatic_forward or is_admin or telegram_user_id in _protected_ids(settings):
        return True
    user = await get_user_by_telegram_id(session, telegram_user_id)
    if user is not None and is_subscription_active(user):
        return True
    await client.delete_message(chat_id, message_id)
    await _log_action(
        session,
        telegram_user_id=telegram_user_id,
        user_id=user.id if user else None,
        target=AccessTarget.discussion,
        action=AccessActionType.delete_message,
        detail=str(message_id),
    )
    # Also try to kick if somehow present without sub
    if settings.discussion_group_id is not None and (
        user is None or not is_subscription_active(user)
    ):
        if telegram_user_id not in _protected_ids(settings):
            try:
                await client.ban(settings.discussion_group_id, telegram_user_id)
            except Exception:  # noqa: BLE001
                logger.exception("ban after illicit discussion message failed")
    await session.flush()
    return False


async def sweep_expired(
    session: AsyncSession,
    client: TelegramAccessClient,
    *,
    settings: Settings | None = None,
) -> int:
    from sqlalchemy import select

    settings = settings or get_settings()
    now = utcnow()
    result = await session.execute(
        select(User).where(
            User.subscription_ends_at.is_not(None),
            User.subscription_ends_at <= now,
            User.channel_access_state != "expired_banned",
        )
    )
    users = list(result.scalars().all())
    count = 0
    for user in users:
        await expire_access(session, client, user.telegram_user_id, settings=settings)
        count += 1
    return count


def _target_for_chat(chat_id: int, settings: Settings) -> AccessTarget | None:
    if settings.channel_id is not None and chat_id == settings.channel_id:
        return AccessTarget.channel
    if settings.discussion_group_id is not None and chat_id == settings.discussion_group_id:
        return AccessTarget.discussion
    return None


DISCUSSION_READ_LIMITATION = """
## Ограничение Telegram: чтение discussion group

Удаление сообщений и kick/ban закрывают *публикацию* и формальное членство,
но стандартная связка channel → discussion group в Telegram не даёт боту
гарантированно запретить *чтение* истории комментариев для пользователя,
который открыл тред через кнопку «Комментировать» под постом канала, если
Telegram показывает комментарии без полноценного join.

Практически:
- Держите и канал, и группу комментариев **приватными**, без username и без
  открытых invite-ссылок.
- Вход в канал — только через join request, который бот одобряет по активной
  подписке.
- Группа комментариев: join requests + проверка подписки на сообщениях
  (удаление + ban).
- Полностью скрыть чтение чужих комментариев «как у неавторизованного»
  штатными Bot API средствами нельзя, если клиент Telegram уже имеет
  доступ к треду через UI канала.

До production владелец должен:
1. Закрыть все старые незащищённые инвайты вручную.
2. Проверить на тестовом аккаунте без подписки, виден ли тред комментариев
   с поста канала после kick/ban.
3. Если чтение всё ещё возможно — не заявлять «полная защита комментариев»;
   рассмотреть альтернативы (отключить discussion / перенести общение в
   отдельный закрытый чат только по инвайту с join request).
""".strip()
