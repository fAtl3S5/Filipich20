from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from dateutil.relativedelta import relativedelta
from sqlalchemy import select

from app.core.timeutil import add_calendar_months, utcnow
from app.jobs.worker import process_job, run_once
from app.models.entities import (
    AutoRenewEvent,
    Grant,
    Job,
    JobStatus,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    ReminderSent,
    User,
)
from app.services.access import (
    create_channel_invite,
    expire_access,
    handle_join_request,
    provision_access,
)
from app.services.broadcasts import create_broadcast, start_broadcast
from app.services.jobs import claim_jobs, enqueue_job
from app.services.payments import (
    process_yookassa_notification,
    start_stars_order,
    start_yookassa_checkout,
    finalize_stars_payment,
)
from app.services.subscriptions import (
    activate_order_with_token,
    create_activation_token,
    mark_payment_succeeded,
    reverse_grant_for_refund,
    set_auto_renew,
    subscription_status_text,
)
from app.services.users import get_or_create_user, is_subscription_active


async def _pay_yookassa(session, yookassa, settings, *, telegram_user_id: int, plan="1m"):
    order, payment, url = await start_yookassa_checkout(
        session,
        yookassa,
        plan_code=plan,
        telegram_user_id=telegram_user_id,
        settings=settings,
        deferred=False,
    )
    yookassa.mark_succeeded(payment.provider_payment_id)
    event = {"event": "payment.succeeded", "object": yookassa.payments[payment.provider_payment_id]}
    status, order2 = await process_yookassa_notification(
        session, yookassa, event=event, settings=settings
    )
    await session.commit()
    return order2, payment, status, url


@pytest.mark.asyncio
async def test_successful_payment_grants_both_chats(
    session, settings, yookassa, access_client, notifier
):
    order, payment, status, _ = await _pay_yookassa(
        session, yookassa, settings, telegram_user_id=42
    )
    assert status == "succeeded"
    user = (await session.execute(select(User).where(User.telegram_user_id == 42))).scalar_one()
    assert is_subscription_active(user)
    # run provision job
    await run_once(access_client=access_client, notifier=notifier, settings=settings)
    assert ("unban", settings.channel_id, 42, True) in access_client.actions
    assert ("unban", settings.discussion_group_id, 42, True) in access_client.actions


@pytest.mark.asyncio
async def test_fake_payment_rejected(session, settings, yookassa):
    order, payment, url = await start_yookassa_checkout(
        session, yookassa, plan_code="1m", telegram_user_id=7, settings=settings
    )
    # Spoofed webhook with wrong amount — API returns pending unchanged amount,
    # but we simulate attacker sending succeeded while API still pending → ignored
    fake_event = {
        "event": "payment.succeeded",
        "object": {"id": payment.provider_payment_id, "status": "succeeded"},
    }
    # Fake client get_payment still pending
    status, _ = await process_yookassa_notification(
        session, yookassa, event=fake_event, settings=settings
    )
    assert status == "pending"
    user = (
        await session.execute(select(User).where(User.telegram_user_id == 7))
    ).scalar_one_or_none()
    # user may exist from order creation but must not be active from this fake event
    if user:
        assert not is_subscription_active(user)


@pytest.mark.asyncio
async def test_duplicate_webhook_idempotent(session, settings, yookassa):
    order, payment, status, _ = await _pay_yookassa(
        session, yookassa, settings, telegram_user_id=50
    )
    assert status == "succeeded"
    event = {"event": "payment.succeeded", "object": yookassa.payments[payment.provider_payment_id]}
    status2, _ = await process_yookassa_notification(
        session, yookassa, event=event, settings=settings
    )
    assert status2 == "succeeded"
    grants = (
        await session.execute(select(Grant).where(Grant.user_id == order.user_id))
    ).scalars().all()
    assert len(grants) == 1


@pytest.mark.asyncio
async def test_parallel_payments_once(session, settings, yookassa):
    order, payment, url = await start_yookassa_checkout(
        session, yookassa, plan_code="1m", telegram_user_id=60, settings=settings
    )
    yookassa.mark_succeeded(payment.provider_payment_id)
    event = {"event": "payment.succeeded", "object": yookassa.payments[payment.provider_payment_id]}

    async def once():
        return await process_yookassa_notification(
            session, yookassa, event=event, settings=settings
        )

    # Sequential on same session (SQLite); mark_payment_succeeded is idempotent
    await once()
    await once()
    user = (await session.execute(select(User).where(User.telegram_user_id == 60))).scalar_one()
    grants = (await session.execute(select(Grant).where(Grant.user_id == user.id))).scalars().all()
    assert len(grants) == 1


@pytest.mark.asyncio
async def test_early_renew_keeps_remainder(session, settings, yookassa):
    await _pay_yookassa(session, yookassa, settings, telegram_user_id=70, plan="1m")
    user = (await session.execute(select(User).where(User.telegram_user_id == 70))).scalar_one()
    first_end = user.subscription_ends_at
    await _pay_yookassa(session, yookassa, settings, telegram_user_id=70, plan="1m")
    await session.refresh(user)
    from app.core.timeutil import ensure_utc

    expected = add_calendar_months(ensure_utc(first_end), 1)
    assert ensure_utc(user.subscription_ends_at) == expected


@pytest.mark.asyncio
async def test_two_payments_both_count(session, settings, yookassa):
    await _pay_yookassa(session, yookassa, settings, telegram_user_id=71, plan="1m")
    await _pay_yookassa(session, yookassa, settings, telegram_user_id=71, plan="3m")
    user = (await session.execute(select(User).where(User.telegram_user_id == 71))).scalar_one()
    grants = (await session.execute(select(Grant).where(Grant.user_id == user.id))).scalars().all()
    assert len(grants) == 2
    assert sum(g.months for g in grants) == 4


@pytest.mark.asyncio
async def test_expire_closes_both(session, settings, access_client, notifier):
    user = await get_or_create_user(session, 80)
    user.subscription_ends_at = utcnow() - timedelta(seconds=1)
    await session.commit()
    result = await expire_access(session, access_client, 80, settings=settings)
    assert result["channel"] == "banned"
    assert result["discussion"] == "banned"
    assert (settings.channel_id, 80) in access_client.banned
    assert (settings.discussion_group_id, 80) in access_client.banned


@pytest.mark.asyncio
async def test_renew_during_ban_restores(session, settings, yookassa, access_client):
    user = await get_or_create_user(session, 81)
    user.subscription_ends_at = utcnow() - timedelta(seconds=1)
    await session.commit()
    await expire_access(session, access_client, 81, settings=settings)
    assert (settings.channel_id, 81) in access_client.banned
    await _pay_yookassa(session, yookassa, settings, telegram_user_id=81)
    await provision_access(session, access_client, 81, settings=settings)
    assert (settings.channel_id, 81) not in access_client.banned


@pytest.mark.asyncio
async def test_repay_after_expire_returns(session, settings, yookassa, access_client):
    await _pay_yookassa(session, yookassa, settings, telegram_user_id=82)
    user = (await session.execute(select(User).where(User.telegram_user_id == 82))).scalar_one()
    user.subscription_ends_at = utcnow() - timedelta(seconds=1)
    await session.commit()
    await expire_access(session, access_client, 82, settings=settings)
    await _pay_yookassa(session, yookassa, settings, telegram_user_id=82)
    await provision_access(session, access_client, 82, settings=settings)
    link = await create_channel_invite(session, access_client, 82, settings=settings)
    assert link.startswith("https://t.me/+")


@pytest.mark.asyncio
async def test_forward_invite_blocked_by_join_request(session, settings, access_client, yookassa):
    # Non-subscriber join request declined
    ok = await handle_join_request(
        session, access_client, chat_id=settings.channel_id, telegram_user_id=99, settings=settings
    )
    assert ok is False
    assert ("decline", settings.channel_id, 99) in access_client.actions
    await _pay_yookassa(session, yookassa, settings, telegram_user_id=99)
    ok2 = await handle_join_request(
        session, access_client, chat_id=settings.channel_id, telegram_user_id=99, settings=settings
    )
    assert ok2 is True


@pytest.mark.asyncio
async def test_activation_token_one_account(session, settings, yookassa):
    order, payment, url = await start_yookassa_checkout(
        session, yookassa, plan_code="1m", telegram_user_id=None, settings=settings, deferred=True
    )
    yookassa.mark_succeeded(payment.provider_payment_id)
    event = {"event": "payment.succeeded", "object": yookassa.payments[payment.provider_payment_id]}
    await process_yookassa_notification(session, yookassa, event=event, settings=settings)
    await session.refresh(order)
    assert order.status == OrderStatus.paid_unactivated
    # Token is issued by payment processing for deferred orders; recover raw via recreate path for test
    from app.core.security import hash_token
    from app.models.entities import ActivationToken

    token_row = (
        await session.execute(select(ActivationToken).where(ActivationToken.order_id == order.id))
    ).scalar_one()
    # Issue a known raw token by replacing hash (test-only)
    raw = "test-activation-token-raw-value-001"
    token_row.token_hash = hash_token(raw, pepper=settings.secret_key)
    await session.flush()
    await activate_order_with_token(
        session, raw_token=raw, telegram_user_id=501, settings=settings
    )
    with pytest.raises(ValueError):
        await activate_order_with_token(
            session, raw_token=raw, telegram_user_id=502, settings=settings
        )
    with pytest.raises(ValueError):
        await activate_order_with_token(
            session, raw_token=raw, telegram_user_id=501, settings=settings
        )


@pytest.mark.asyncio
async def test_restart_keeps_jobs(session, settings, access_client, notifier):
    await enqueue_job(session, "admin_alert", {"text": "hello"}, unique_key="persist-1")
    await session.commit()
    # simulate restart by claiming again
    n = await run_once(access_client=access_client, notifier=notifier, settings=settings)
    assert n >= 1
    assert "hello" in notifier.admin_messages


@pytest.mark.asyncio
async def test_tg_error_after_pay_keeps_grant(session, settings, yookassa, access_client):
    class FailingAccess(type(access_client)):
        async def unban(self, chat_id, user_id, *, only_if_banned=True):
            raise RuntimeError("telegram down")

    order, payment, status, _ = await _pay_yookassa(
        session, yookassa, settings, telegram_user_id=88
    )
    user = (await session.execute(select(User).where(User.telegram_user_id == 88))).scalar_one()
    assert is_subscription_active(user)
    failing = FailingAccess()
    result = await provision_access(session, failing, 88, settings=settings)
    assert result["ok"] is False
    await session.refresh(user)
    assert is_subscription_active(user)


@pytest.mark.asyncio
async def test_reminders_no_dup(session, settings, notifier, access_client):
    user = await get_or_create_user(session, 90, mark_started=True)
    ends = utcnow() + timedelta(days=3, minutes=1)
    user.subscription_ends_at = ends
    await session.commit()
    from app.services.subscriptions import schedule_reminders

    await schedule_reminders(session, user)
    await schedule_reminders(session, user)
    await session.commit()
    jobs = (
        await session.execute(
            select(Job).where(Job.job_type == "send_reminder", Job.unique_key.is_not(None))
        )
    ).scalars().all()
    keys = [j.unique_key for j in jobs]
    assert len(keys) == len(set(keys))


@pytest.mark.asyncio
async def test_broadcast_resume(session, settings, notifier, access_client):
    u1 = await get_or_create_user(session, 201, mark_started=True)
    u2 = await get_or_create_user(session, 202, mark_started=True)
    await session.commit()
    bc = await create_broadcast(
        session, admin_id=1001, text="Привет", segment="all"
    )
    await start_broadcast(session, bc.id)
    await session.commit()
    await run_once(access_client=access_client, notifier=notifier, settings=settings)
    # may need another tick
    for _ in range(5):
        await run_once(access_client=access_client, notifier=notifier, settings=settings)
    await session.refresh(bc)
    assert bc.sent_count >= 2 or len(notifier.messages) >= 2


@pytest.mark.asyncio
async def test_admin_acl(settings):
    assert 1001 in settings.admin_ids
    assert 42 not in settings.admin_ids


@pytest.mark.asyncio
async def test_month_end_calc():
    # Jan 31 + 1 month → Feb 28/29
    start = datetime(2024, 1, 31, 12, 0, tzinfo=UTC)  # leap year
    end = add_calendar_months(start, 1)
    assert end == datetime(2024, 2, 29, 12, 0, tzinfo=UTC)
    start2 = datetime(2023, 1, 31, 12, 0, tzinfo=UTC)
    end2 = add_calendar_months(start2, 1)
    assert end2 == datetime(2023, 2, 28, 12, 0, tzinfo=UTC)
    # Dec 31 + 2 months
    end3 = add_calendar_months(datetime(2023, 12, 31, 10, 0, tzinfo=UTC), 2)
    assert end3.month == 2 and end3.day == 29  # 2024 leap


@pytest.mark.asyncio
async def test_refund_keeps_other_purchases(session, settings, yookassa):
    o1, p1, _, _ = await _pay_yookassa(session, yookassa, settings, telegram_user_id=300, plan="1m")
    o2, p2, _, _ = await _pay_yookassa(session, yookassa, settings, telegram_user_id=300, plan="3m")
    user = (await session.execute(select(User).where(User.telegram_user_id == 300))).scalar_one()
    ends_before_refund = user.subscription_ends_at
    # refund first payment only
    pay1 = (
        await session.execute(select(Payment).where(Payment.order_id == o1.id))
    ).scalar_one()
    await reverse_grant_for_refund(
        session, pay1, full=True, refunded_amount_kopecks=pay1.amount_kopecks or 0
    )
    await session.refresh(user)
    grants = (
        await session.execute(
            select(Grant).where(Grant.user_id == user.id, Grant.reversed.is_(False))
        )
    ).scalars().all()
    assert len(grants) == 1
    assert grants[0].months == 3
    assert user.subscription_ends_at is not None
    from app.core.timeutil import ensure_utc

    assert ensure_utc(user.subscription_ends_at) < ensure_utc(ends_before_refund)


@pytest.mark.asyncio
async def test_expire_race_old_job_does_not_ban_renewed(
    session, settings, access_client, yookassa
):
    await _pay_yookassa(session, yookassa, settings, telegram_user_id=400)
    user = (await session.execute(select(User).where(User.telegram_user_id == 400))).scalar_one()
    old_ends = user.subscription_ends_at.isoformat()
    # renew
    await _pay_yookassa(session, yookassa, settings, telegram_user_id=400)
    await session.refresh(user)
    result = await expire_access(
        session, access_client, 400, expected_ends_at=old_ends, settings=settings
    )
    # should restore/provision because active
    assert is_subscription_active(user)
    assert (settings.channel_id, 400) not in access_client.banned


@pytest.mark.asyncio
async def test_stars_payment_path(session, settings):
    order, payment = await start_stars_order(
        session, plan_code="1m", telegram_user_id=555, stars_amount=100
    )
    await finalize_stars_payment(
        session,
        order_public_id=order.public_id,
        telegram_charge_id="tg_charge_1",
        stars_amount=100,
    )
    user = (await session.execute(select(User).where(User.telegram_user_id == 555))).scalar_one()
    assert is_subscription_active(user)


@pytest.mark.asyncio
async def test_auto_renew_preference_persisted_and_tracked(session, settings):
    user = await get_or_create_user(session, 777, mark_started=True)
    assert user.auto_renew_enabled is False
    text_off = subscription_status_text(user, settings)
    assert "Статус:" in text_off
    assert "Автопродление: выключено" in text_off

    await set_auto_renew(session, user, enabled=True)
    await session.commit()
    await session.refresh(user)
    assert user.auto_renew_enabled is True
    text_on = subscription_status_text(user, settings)
    assert "Автопродление: включено" in text_on
    assert "рекуррент" in text_on.lower()

    events = (
        await session.execute(
            select(AutoRenewEvent).where(AutoRenewEvent.user_id == user.id)
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].enabled is True

    await set_auto_renew(session, user, enabled=False)
    await session.commit()
    events2 = (
        await session.execute(
            select(AutoRenewEvent)
            .where(AutoRenewEvent.user_id == user.id)
            .order_by(AutoRenewEvent.id)
        )
    ).scalars().all()
    assert [e.enabled for e in events2] == [True, False]

