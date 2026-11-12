from __future__ import annotations

import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import SupportTicket, User


async def create_support_ticket(
    session: AsyncSession, user: User, message: str
) -> SupportTicket:
    ticket = SupportTicket(
        public_number=f"S-{secrets.token_hex(3).upper()}",
        user_id=user.id,
        telegram_user_id=user.telegram_user_id,
        message=message,
    )
    session.add(ticket)
    await session.flush()
    return ticket
