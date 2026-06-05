from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_profiles"
down_revision: str | None = "0003_nodes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column(
            "provider_kind",
            sa.Enum(
                "xray",
                "sing-box",
                "hysteria",
                "wireguard",
                name="provider_kind",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("protocol", sa.String(length=64), nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["nodes.id"],
            name="fk_profiles_node_id_nodes",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_profiles"),
        sa.UniqueConstraint("slug", name="uq_profiles_slug"),
    )
    op.create_index("ix_profiles_provider_kind", "profiles", ["provider_kind"])
    op.create_index("ix_profiles_node_id", "profiles", ["node_id"])
    op.create_index("ix_profiles_is_active", "profiles", ["is_active"])
    op.create_index(
        "ix_profiles_created_at_id",
        "profiles",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_profiles_created_at_id", table_name="profiles")
    op.drop_index("ix_profiles_is_active", table_name="profiles")
    op.drop_index("ix_profiles_node_id", table_name="profiles")
    op.drop_index("ix_profiles_provider_kind", table_name="profiles")
    op.drop_table("profiles")
