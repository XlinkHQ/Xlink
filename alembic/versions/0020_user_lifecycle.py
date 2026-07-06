from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_user_lifecycle"
down_revision: str = "0019_xray_core_template"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "data_reset_strategy", sa.String(length=16), nullable=False, server_default="no_reset"
        ),
    )
    op.add_column("users", sa.Column("last_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users", sa.Column("on_hold", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("users", sa.Column("on_hold_duration_seconds", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("device_limit", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("owner_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_users_owner_id", "users", "users", ["owner_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_owner_id", "users", type_="foreignkey")
    for col in (
        "owner_id",
        "device_limit",
        "on_hold_duration_seconds",
        "on_hold",
        "last_reset_at",
        "data_reset_strategy",
    ):
        op.drop_column("users", col)
