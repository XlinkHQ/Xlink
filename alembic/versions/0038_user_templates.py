from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_user_templates"
down_revision: str = "0037_admin_quotas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_templates",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("data_limit_bytes", sa.BigInteger(), nullable=True),
        sa.Column("expire_days", sa.Integer(), nullable=True),
        sa.Column("data_reset_strategy", sa.String(length=16), nullable=False, server_default="no_reset"),
        sa.Column("device_limit", sa.Integer(), nullable=True),
        sa.Column("username_prefix", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_templates_name", "user_templates", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_templates_name", table_name="user_templates")
    op.drop_table("user_templates")
