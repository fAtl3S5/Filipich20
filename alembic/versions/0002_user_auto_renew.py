"""Add users.auto_renew_enabled preference and auto_renew_events.

Revision ID: 0002_user_auto_renew
Revises: 0001_initial
Create Date: 2026-11-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_user_auto_renew"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "auto_renew_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_table(
        "auto_renew_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_auto_renew_events_user_id", "auto_renew_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_auto_renew_events_user_id", table_name="auto_renew_events")
    op.drop_table("auto_renew_events")
    op.drop_column("users", "auto_renew_enabled")
