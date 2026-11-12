from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.db import Base
from app.jobs.worker import NullNotifier
from app.payments.yookassa import FakeYooKassaClient
from app.services.access import NullTelegramAccessClient


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    from app.core import db as dbmod

    dbmod.engine = eng
    dbmod.SessionLocal = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    from app.core.db import SessionLocal

    async with SessionLocal() as session:
        yield session
        await session.commit()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        secret_key="test-secret",
        admin_ids=[1001],
        channel_id=-100111,
        discussion_group_id=-100222,
        ban_allowlist=[9001],
        enable_web_yookassa=True,
        enable_bot_initiated_yookassa=False,
        enable_stars=True,
        stars_price_1m=100,
        stars_price_3m=250,
        stars_price_6m=450,
        stars_price_12m=800,
        bot_token="123:ABC",
        display_timezone="Asia/Novosibirsk",
    )


@pytest.fixture
def access_client() -> NullTelegramAccessClient:
    return NullTelegramAccessClient()


@pytest.fixture
def yookassa() -> FakeYooKassaClient:
    return FakeYooKassaClient()


@pytest.fixture
def notifier() -> NullNotifier:
    return NullNotifier()
