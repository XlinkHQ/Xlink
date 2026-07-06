from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_user_expire_strategy"
down_revision: str = "0022_config_remark"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "expire_strategy",
            sa.String(length=24),
            nullable=False,
            server_default="never",
        ),
    )
    op.add_column(
        "users",
        sa.Column("activation_deadline", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("removed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_users_removed", "users", ["removed"])

    op.execute("UPDATE users SET expire_strategy = 'start_on_first_use' WHERE on_hold = true")
    op.execute(
        "UPDATE users SET expire_strategy = 'fixed_date' "
        "WHERE on_hold = false AND expire_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_users_removed", table_name="users")
    op.drop_column("users", "removed")
    op.drop_column("users", "activation_deadline")
    op.drop_column("users", "expire_strategy")
