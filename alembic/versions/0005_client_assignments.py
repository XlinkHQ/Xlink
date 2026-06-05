from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_client_assignments"
down_revision: str | None = "0004_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "client_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("provider_client_id", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "disabled",
                "expired",
                name="assignment_status",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("traffic_limit_bytes", sa.BigInteger(), nullable=True),
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
            ["user_id"],
            ["users.id"],
            name="fk_client_assignments_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name="fk_client_assignments_profile_id_profiles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["nodes.id"],
            name="fk_client_assignments_node_id_nodes",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_client_assignments"),
        sa.UniqueConstraint(
            "user_id", "profile_id", "node_id", name="uq_client_assignments_triplet"
        ),
    )
    op.create_index("ix_client_assignments_user_id", "client_assignments", ["user_id"])
    op.create_index("ix_client_assignments_profile_id", "client_assignments", ["profile_id"])
    op.create_index("ix_client_assignments_node_id", "client_assignments", ["node_id"])
    op.create_index("ix_client_assignments_provider_kind", "client_assignments", ["provider_kind"])
    op.create_index("ix_client_assignments_status", "client_assignments", ["status"])
    op.create_index("ix_client_assignments_expires_at", "client_assignments", ["expires_at"])
    op.create_index(
        "ix_client_assignments_created_at_id",
        "client_assignments",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_client_assignments_created_at_id", table_name="client_assignments")
    op.drop_index("ix_client_assignments_expires_at", table_name="client_assignments")
    op.drop_index("ix_client_assignments_status", table_name="client_assignments")
    op.drop_index("ix_client_assignments_provider_kind", table_name="client_assignments")
    op.drop_index("ix_client_assignments_node_id", table_name="client_assignments")
    op.drop_index("ix_client_assignments_profile_id", table_name="client_assignments")
    op.drop_index("ix_client_assignments_user_id", table_name="client_assignments")
    op.drop_table("client_assignments")
