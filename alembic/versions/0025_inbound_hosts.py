from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0025_inbound_hosts"
down_revision: str = "0024_admin_capabilities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inbound_hosts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("profile_id", UUID(as_uuid=True), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("sni", sa.String(length=255), nullable=True),
        sa.Column("host", sa.String(length=255), nullable=True),
        sa.Column("path", sa.String(length=512), nullable=True),
        sa.Column("alpn", sa.String(length=64), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=True),
        sa.Column("security", sa.String(length=16), nullable=True),
        sa.Column("network", sa.String(length=32), nullable=True),
        sa.Column("fragment", sa.String(length=255), nullable=True),
        sa.Column("noise", sa.String(length=255), nullable=True),
        sa.Column("mux", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allow_insecure", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_universal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("chain_target_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chain_target_id"], ["inbound_hosts.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_inbound_hosts_profile", "inbound_hosts", ["profile_id"])
    op.create_index("ix_inbound_hosts_universal", "inbound_hosts", ["is_universal"])


def downgrade() -> None:
    op.drop_index("ix_inbound_hosts_universal", table_name="inbound_hosts")
    op.drop_index("ix_inbound_hosts_profile", table_name="inbound_hosts")
    op.drop_table("inbound_hosts")
