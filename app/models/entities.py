from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)


from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def _enum(enum_cls, name: str):
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        values_callable=lambda x: [e.value for e in x],
    )

from app.core.db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


class OrderStatus(str, enum.Enum):
    pending = "pending"
    paid_unactivated = "paid_unactivated"
    paid = "paid"
    canceled = "canceled"
    refunded = "refunded"
    partially_refunded = "partially_refunded"


class PaymentProvider(str, enum.Enum):
    yookassa = "yookassa"
    stars = "stars"
    manual = "manual"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    succeeded = "succeeded"
    canceled = "canceled"
    refunded = "refunded"
    partially_refunded = "partially_refunded"


class GrantSource(str, enum.Enum):
    payment = "payment"
    activation = "activation"
    manual = "manual"
    refund_reversal = "refund_reversal"


class AccessTarget(str, enum.Enum):
    channel = "channel"
    discussion = "discussion"


class AccessActionType(str, enum.Enum):
    unban = "unban"
    ban_expire = "ban_expire"
    ban_manual = "ban_manual"
    approve_join = "approve_join"
    decline_join = "decline_join"
    delete_message = "delete_message"
    invite_sent = "invite_sent"


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    canceled = "canceled"


class BroadcastStatus(str, enum.Enum):
    draft = "draft"
    confirmed = "confirmed"
    sending = "sending"
    paused = "paused"
    done = "done"
    canceled = "canceled"


class ReminderType(str, enum.Enum):
    d3 = "d3"
    d1 = "d1"
    expired = "expired"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked_bot: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    broadcasts_opt_out: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    subscription_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    channel_access_state: Mapped[str] = mapped_column(String(32), default="unknown")
    discussion_access_state: Mapped[str] = mapped_column(String(32), default="unknown")
    manual_ban_channel: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    manual_ban_discussion: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    orders: Mapped[list[Order]] = relationship(back_populates="user")
    grants: Mapped[list[Grant]] = relationship(back_populates="user")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    plan_code: Mapped[str] = mapped_column(String(16))
    months: Mapped[int] = mapped_column(Integer)
    amount_kopecks: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    stars_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        _enum(OrderStatus, "order_status"), default=OrderStatus.pending
    )
    provider: Mapped[PaymentProvider] = mapped_column(_enum(PaymentProvider, "payment_provider"))
    deferred_activation: Mapped[bool] = mapped_column(Boolean, default=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_by_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User | None] = relationship(back_populates="orders")
    payments: Mapped[list[Payment]] = relationship(back_populates="order")
    grants: Mapped[list[Grant]] = relationship(back_populates="order")
    activation_token: Mapped[ActivationToken | None] = relationship(
        back_populates="order", uselist=False
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "provider_payment_id", name="uq_provider_payment"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    provider: Mapped[PaymentProvider] = mapped_column(_enum(PaymentProvider, "payment_provider"))
    provider_payment_id: Mapped[str] = mapped_column(String(128))
    idempotence_key: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[PaymentStatus] = mapped_column(
        _enum(PaymentStatus, "payment_status"), default=PaymentStatus.pending
    )
    amount_kopecks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    stars_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    telegram_charge_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    succeeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_amount_kopecks: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    order: Mapped[Order] = relationship(back_populates="payments")


class Grant(Base):
    __tablename__ = "grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), nullable=True)
    source: Mapped[GrantSource] = mapped_column(_enum(GrantSource, "grant_source"))
    months: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delta_days: Mapped[int] = mapped_column(Integer, default=0)
    reversed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="grants")
    order: Mapped[Order | None] = relationship(back_populates="grants")


class ActivationToken(Base):
    __tablename__ = "activation_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    order: Mapped[Order] = relationship(back_populates="activation_token")


class AccessAction(Base):
    __tablename__ = "access_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    target: Mapped[AccessTarget] = mapped_column(_enum(AccessTarget, "access_target"))
    action: Mapped[AccessActionType] = mapped_column(
        _enum(AccessActionType, "access_action_type")
    )
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ReminderSent(Base):
    __tablename__ = "reminders_sent"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "ends_at_version", "reminder_type", name="uq_reminder_version"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    ends_at_version: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reminder_type: Mapped[ReminderType] = mapped_column(
        _enum(ReminderType, "reminder_type")
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by_admin_id: Mapped[int] = mapped_column(BigInteger)
    segment: Mapped[str] = mapped_column(String(32), default="all")
    status: Mapped[BroadcastStatus] = mapped_column(
        _enum(BroadcastStatus, "broadcast_status"), default=BroadcastStatus.draft
    )
    text: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    media_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    buttons_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONType, nullable=True)
    total_targets: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    cursor_user_id: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BroadcastDelivery(Base):
    __tablename__ = "broadcast_deliveries"
    __table_args__ = (
        UniqueConstraint("broadcast_id", "user_id", name="uq_broadcast_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broadcast_id: Mapped[int] = mapped_column(ForeignKey("broadcasts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_run_at", "status", "run_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64), index=True)
    unique_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus, "job_status"), default=JobStatus.pending, index=True
    )
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=10)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AdminAction(Base):
    __tablename__ = "admin_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(64))
    target_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_number: Mapped[str] = mapped_column(String(32), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    telegram_user_id: Mapped[int] = mapped_column(BigInteger)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
