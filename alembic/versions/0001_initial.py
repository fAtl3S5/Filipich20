"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255)),
        sa.Column("full_name", sa.String(512)),
        sa.Column("language_code", sa.String(16)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("blocked_bot", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("broadcasts_opt_out", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("subscription_ends_at", sa.DateTime(timezone=True)),
        sa.Column("channel_access_state", sa.String(32), server_default="unknown"),
        sa.Column("discussion_access_state", sa.String(32), server_default="unknown"),
        sa.Column("manual_ban_channel", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("manual_ban_discussion", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_telegram_user_id", "users", ["telegram_user_id"], unique=True)
    op.create_index("ix_users_subscription_ends_at", "users", ["subscription_ends_at"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(40), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("telegram_user_id", sa.BigInteger()),
        sa.Column("plan_code", sa.String(16), nullable=False),
        sa.Column("months", sa.Integer(), nullable=False),
        sa.Column("amount_kopecks", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(8), server_default="RUB"),
        sa.Column("stars_amount", sa.Integer()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("deferred_activation", sa.Boolean(), server_default="false"),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("activated_by_telegram_id", sa.BigInteger()),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_orders_public_id", "orders", ["public_id"], unique=True)
    op.create_index("ix_orders_telegram_user_id", "orders", ["telegram_user_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_payment_id", sa.String(128), nullable=False),
        sa.Column("idempotence_key", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("amount_kopecks", sa.Integer()),
        sa.Column("currency", sa.String(8)),
        sa.Column("stars_amount", sa.Integer()),
        sa.Column("telegram_charge_id", sa.String(128)),
        sa.Column("raw_payload", sa.JSON()),
        sa.Column("succeeded_at", sa.DateTime(timezone=True)),
        sa.Column("refunded_amount_kopecks", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_payment_id", name="uq_provider_payment"),
    )
    op.create_index("ix_payments_order_id", "payments", ["order_id"])

    op.create_table(
        "grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id")),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id")),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("months", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delta_days", sa.Integer(), server_default="0"),
        sa.Column("reversed", sa.Boolean(), server_default="false"),
        sa.Column("reason", sa.Text()),
        sa.Column("admin_id", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_grants_user_id", "grants", ["user_id"])

    op.create_table(
        "activation_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), unique=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("used_by_telegram_id", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_activation_tokens_token_hash", "activation_tokens", ["token_hash"], unique=True)

    op.create_table(
        "access_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("target", sa.String(32), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("success", sa.Boolean(), server_default="true"),
        sa.Column("detail", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_access_actions_telegram_user_id", "access_actions", ["telegram_user_id"])

    op.create_table(
        "reminders_sent",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ends_at_version", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reminder_type", sa.String(16), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "ends_at_version", "reminder_type", name="uq_reminder_version"),
    )

    op.create_table(
        "broadcasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_by_admin_id", sa.BigInteger(), nullable=False),
        sa.Column("segment", sa.String(32), server_default="all"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("media_type", sa.String(16)),
        sa.Column("media_file_id", sa.String(256)),
        sa.Column("buttons_json", sa.JSON()),
        sa.Column("total_targets", sa.Integer(), server_default="0"),
        sa.Column("sent_count", sa.Integer(), server_default="0"),
        sa.Column("failed_count", sa.Integer(), server_default="0"),
        sa.Column("cursor_user_id", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "broadcast_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("broadcast_id", sa.Integer(), sa.ForeignKey("broadcasts.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending"),
        sa.Column("error", sa.Text()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("broadcast_id", "user_id", name="uq_broadcast_user"),
    )
    op.create_index("ix_broadcast_deliveries_broadcast_id", "broadcast_deliveries", ["broadcast_id"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("unique_key", sa.String(128), unique=True),
        sa.Column("payload", sa.JSON(), server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("attempts", sa.Integer(), server_default="0"),
        sa.Column("max_attempts", sa.Integer(), server_default="10"),
        sa.Column("last_error", sa.Text()),
        sa.Column("locked_by", sa.String(64)),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_job_type", "jobs", ["job_type"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_status_run_at", "jobs", ["status", "run_at"])

    op.create_table(
        "admin_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_user_id", sa.BigInteger()),
        sa.Column("detail", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_admin_actions_admin_id", "admin_actions", ["admin_id"])

    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_number", sa.String(32), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    for table in [
        "support_tickets",
        "admin_actions",
        "jobs",
        "broadcast_deliveries",
        "broadcasts",
        "reminders_sent",
        "access_actions",
        "activation_tokens",
        "grants",
        "payments",
        "orders",
        "users",
    ]:
        op.drop_table(table)
