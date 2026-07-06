from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_app_settings"
down_revision: str = "0013_groups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_title", sa.String(length=255), nullable=False, server_default="XLink"),
        sa.Column("support_link", sa.String(length=512), nullable=False, server_default=""),
        sa.Column(
            "update_interval_hours", sa.Integer(), nullable=False, server_default=sa.text("12")
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.execute(
        "INSERT INTO app_settings (id, profile_title, support_link, update_interval_hours) "
        "VALUES (1, 'XLink', '', 12)"
    )


def downgrade() -> None:
    op.drop_table("app_settings")
