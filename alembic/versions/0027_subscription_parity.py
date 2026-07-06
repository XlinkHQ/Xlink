from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_subscription_parity"
down_revision: str = "0026_node_usage_coefficient"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("shuffle_configs", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "app_settings",
        sa.Column(
            "placeholder_if_disabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.add_column(
        "app_settings",
        sa.Column(
            "placeholder_remark",
            sa.String(length=255),
            nullable=False,
            server_default="Subscription disabled — contact support",
        ),
    )
    op.add_column(
        "app_settings",
        sa.Column("subscription_rules", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "users",
        sa.Column("sub_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("sub_last_user_agent", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "sub_last_user_agent")
    op.drop_column("users", "sub_updated_at")
    op.drop_column("app_settings", "subscription_rules")
    op.drop_column("app_settings", "placeholder_remark")
    op.drop_column("app_settings", "placeholder_if_disabled")
    op.drop_column("app_settings", "shuffle_configs")
