from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_nodes"
down_revision: str | None = "0002_user_listing_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "disabled",
                "offline",
                name="node_status",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_users", sa.Integer(), nullable=False),
        sa.Column("current_users", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_nodes"),
        sa.UniqueConstraint("slug", name="uq_nodes_slug"),
    )
    op.create_index("ix_nodes_host", "nodes", ["host"])
    op.create_index("ix_nodes_status", "nodes", ["status"])
    op.create_index("ix_nodes_last_seen_at", "nodes", ["last_seen_at"])
    op.create_index(
        "ix_nodes_created_at_id",
        "nodes",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_nodes_status_created_id",
        "nodes",
        ["status", sa.text("created_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_nodes_status_created_id", table_name="nodes")
    op.drop_index("ix_nodes_created_at_id", table_name="nodes")
    op.drop_index("ix_nodes_last_seen_at", table_name="nodes")
    op.drop_index("ix_nodes_status", table_name="nodes")
    op.drop_index("ix_nodes_host", table_name="nodes")
    op.drop_table("nodes")
