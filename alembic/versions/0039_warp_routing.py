from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_warp_routing"
down_revision: str = "0038_user_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("warp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("app_settings", sa.Column("warp_private_key", sa.String(length=128), nullable=False, server_default=""))
    op.add_column("app_settings", sa.Column("warp_public_key", sa.String(length=128), nullable=False, server_default=""))
    op.add_column("app_settings", sa.Column("warp_address", sa.String(length=255), nullable=False, server_default=""))
    op.add_column(
        "app_settings",
        sa.Column("warp_endpoint", sa.String(length=255), nullable=False, server_default="engage.cloudflareclient.com:2408"),
    )
    op.add_column("app_settings", sa.Column("warp_reserved", sa.String(length=64), nullable=False, server_default=""))

    op.create_table(
        "routing_rules",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("match_type", sa.String(length=16), nullable=False, server_default="domain"),
        sa.Column("match_values", sa.Text(), nullable=False, server_default=""),
        sa.Column("outbound", sa.String(length=16), nullable=False, server_default="block"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("routing_rules")
    for col in (
        "warp_reserved", "warp_endpoint", "warp_address",
        "warp_public_key", "warp_private_key", "warp_enabled",
    ):
        op.drop_column("app_settings", col)
