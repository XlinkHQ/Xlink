from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_notification_settings"
down_revision: str = "0034_user_node_pinning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("notify_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "app_settings",
        sa.Column("notify_expiring_days", sa.Integer(), server_default="3", nullable=False),
    )
    op.add_column(
        "app_settings",
        sa.Column("notify_usage_percent", sa.Integer(), server_default="80", nullable=False),
    )
    op.add_column(
        "app_settings",
        sa.Column("notify_node_down", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "app_settings",
        sa.Column("webhook_address", sa.String(length=1024), server_default="", nullable=False),
    )
    op.add_column(
        "app_settings",
        sa.Column("discord_webhook_url", sa.String(length=1024), server_default="", nullable=False),
    )
    op.add_column(
        "app_settings",
        sa.Column("telegram_bot_token", sa.String(length=255), server_default="", nullable=False),
    )
    op.add_column(
        "app_settings",
        sa.Column("telegram_chat_ids", sa.String(length=1024), server_default="", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "telegram_chat_ids")
    op.drop_column("app_settings", "telegram_bot_token")
    op.drop_column("app_settings", "discord_webhook_url")
    op.drop_column("app_settings", "webhook_address")
    op.drop_column("app_settings", "notify_node_down")
    op.drop_column("app_settings", "notify_usage_percent")
    op.drop_column("app_settings", "notify_expiring_days")
    op.drop_column("app_settings", "notify_enabled")
