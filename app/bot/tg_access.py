from __future__ import annotations

from aiogram import Bot


class AiogramAccessClient:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def unban(self, chat_id: int, user_id: int, *, only_if_banned: bool = True) -> bool:
        await self.bot.unban_chat_member(chat_id, user_id, only_if_banned=only_if_banned)
        return True

    async def ban(self, chat_id: int, user_id: int) -> bool:
        await self.bot.ban_chat_member(chat_id, user_id)
        return True

    async def approve_join_request(self, chat_id: int, user_id: int) -> bool:
        await self.bot.approve_chat_join_request(chat_id, user_id)
        return True

    async def decline_join_request(self, chat_id: int, user_id: int) -> bool:
        await self.bot.decline_chat_join_request(chat_id, user_id)
        return True

    async def create_chat_invite_link(
        self, chat_id: int, *, creates_join_request: bool = True, name: str | None = None
    ) -> str:
        link = await self.bot.create_chat_invite_link(
            chat_id,
            name=name,
            creates_join_request=creates_join_request,
        )
        return link.invite_link

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        await self.bot.delete_message(chat_id, message_id)
        return True

    async def get_chat_member_status(self, chat_id: int, user_id: int) -> str:
        member = await self.bot.get_chat_member(chat_id, user_id)
        return member.status
