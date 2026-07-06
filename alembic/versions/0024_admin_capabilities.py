from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_admin_capabilities"
down_revision: str = "0023_user_expire_strategy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_sudo", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("all_groups_access", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "users",
        sa.Column("modify_users_access", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "users",
        sa.Column("subscription_url_prefix", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("users_data_usage", sa.BigInteger(), nullable=False, server_default="0"),
    )

    op.create_table(
        "admin_groups",
        sa.Column("admin_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("admin_id", "group_id"),
    )

    op.execute("UPDATE users SET is_sudo = true WHERE role = 'admin'")


def downgrade() -> None:
    op.drop_table("admin_groups")
    op.drop_column("users", "users_data_usage")
    op.drop_column("users", "subscription_url_prefix")
    op.drop_column("users", "modify_users_access")
    op.drop_column("users", "all_groups_access")
    op.drop_column("users", "is_sudo")
