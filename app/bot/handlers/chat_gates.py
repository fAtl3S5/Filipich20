from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import ChatJoinRequest, ChatMemberUpdated, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.services.access import (
    TelegramAccessClient,
    enforce_discussion_message,
    handle_join_request,
)

router = Router(name="chat_gates")


@router.chat_join_request()
async def on_join_request(
    event: ChatJoinRequest,
    session: AsyncSession,
    settings: Settings,
    access_client: TelegramAccessClient,
) -> None:
    await handle_join_request(
        session,
        access_client,
        chat_id=event.chat.id,
        telegram_user_id=event.from_user.id,
        settings=settings,
    )


@router.chat_member()
async def on_chat_member(
    event: ChatMemberUpdated,
    session: AsyncSession,
    settings: Settings,
    access_client: TelegramAccessClient,
) -> None:
    # Track leaves; if somehow joined without approval path, re-check
    new = event.new_chat_member
    if new.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED}:
        from app.services.users import get_user_by_telegram_id, is_subscription_active

        user = await get_user_by_telegram_id(session, new.user.id)
        if user is None or not is_subscription_active(user):
            if new.user.id not in settings.admin_ids and new.user.id not in settings.ban_allowlist:
                chat_id = event.chat.id
                if chat_id in {settings.channel_id, settings.discussion_group_id}:
                    await access_client.ban(chat_id, new.user.id)


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def on_group_message(
    message: Message,
    session: AsyncSession,
    settings: Settings,
    access_client: TelegramAccessClient,
) -> None:
    if settings.discussion_group_id is None or message.chat.id != settings.discussion_group_id:
        return
    if message.from_user is None:
        return
    is_auto = bool(getattr(message, "is_automatic_forward", False) or message.forward_from_chat)
    is_admin = message.from_user.id in settings.admin_ids
    await enforce_discussion_message(
        session,
        access_client,
        chat_id=message.chat.id,
        telegram_user_id=message.from_user.id,
        message_id=message.message_id,
        is_automatic_forward=is_auto,
        is_admin=is_admin,
        settings=settings,
    )
