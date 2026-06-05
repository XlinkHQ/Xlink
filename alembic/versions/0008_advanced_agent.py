from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_advanced_agent"
down_revision: str | None = "0007_traffic_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "node_commands",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "apply_config",
                "reload",
                "restart",
                "upgrade",
                "rollback",
                "collect_diagnostics",
                "provider_healthcheck",
                name="node_command_kind",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "leased",
                "succeeded",
                "failed",
                "expired",
                "cancelled",
                name="node_command_status",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("payload", _JSON, nullable=False),
        sa.Column("signature", sa.String(length=128), nullable=False),
        sa.Column("origin", sa.String(length=64), nullable=False),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("leased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("result", _JSON, nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["node_id"], ["nodes.id"], name="fk_node_commands_node_id_nodes", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_node_commands"),
    )
    op.create_index("ix_node_commands_node_id", "node_commands", ["node_id"])
    op.create_index("ix_node_commands_status", "node_commands", ["status"])
    op.create_index("ix_node_commands_node_status", "node_commands", ["node_id", "status"])
    op.create_index(
        "ix_node_commands_created_at_id",
        "node_commands",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )

    op.create_table(
        "node_drift_reports",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("desired_version", sa.String(length=64), nullable=False),
        sa.Column("reported_version", sa.String(length=64), nullable=True),
        sa.Column(
            "severity",
            sa.Enum(
                "none",
                "low",
                "medium",
                "high",
                name="node_drift_severity",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("drift", _JSON, nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("remediated", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["nodes.id"],
            name="fk_node_drift_reports_node_id_nodes",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_node_drift_reports"),
    )
    op.create_index("ix_node_drift_reports_node_id", "node_drift_reports", ["node_id"])
    op.create_index("ix_node_drift_reports_severity", "node_drift_reports", ["severity"])
    op.create_index(
        "ix_node_drift_reports_node_detected",
        "node_drift_reports",
        ["node_id", sa.text("detected_at DESC")],
    )

    op.create_table(
        "node_provider_health",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "healthy",
                "degraded",
                "unhealthy",
                "unknown",
                name="node_provider_health_status",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["nodes.id"],
            name="fk_node_provider_health_node_id_nodes",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_node_provider_health"),
    )
    op.create_index("ix_node_provider_health_node_id", "node_provider_health", ["node_id"])
    op.create_index(
        "ix_node_provider_health_node_provider",
        "node_provider_health",
        ["node_id", "provider_name"],
    )
    op.create_index(
        "ix_node_provider_health_checked",
        "node_provider_health",
        [sa.text("checked_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_node_provider_health_checked", table_name="node_provider_health")
    op.drop_index("ix_node_provider_health_node_provider", table_name="node_provider_health")
    op.drop_index("ix_node_provider_health_node_id", table_name="node_provider_health")
    op.drop_table("node_provider_health")
    op.drop_index("ix_node_drift_reports_node_detected", table_name="node_drift_reports")
    op.drop_index("ix_node_drift_reports_severity", table_name="node_drift_reports")
    op.drop_index("ix_node_drift_reports_node_id", table_name="node_drift_reports")
    op.drop_table("node_drift_reports")
    op.drop_index("ix_node_commands_created_at_id", table_name="node_commands")
    op.drop_index("ix_node_commands_node_status", table_name="node_commands")
    op.drop_index("ix_node_commands_status", table_name="node_commands")
    op.drop_index("ix_node_commands_node_id", table_name="node_commands")
    op.drop_table("node_commands")
