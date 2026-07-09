from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0049_traffic_hourly_rollup"
down_revision: str = "0048_group_profiles_join"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BIGINT = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "traffic_hourly",
        sa.Column("id", _BIGINT, autoincrement=True, nullable=False),
        sa.Column("assignment_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("node_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("hour_bucket", sa.DateTime(timezone=True), nullable=False),
        sa.Column("upload_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("download_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["client_assignments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_traffic_hourly"),
        sa.UniqueConstraint(
            "assignment_id", "hour_bucket", name="uq_traffic_hourly_assignment_bucket"
        ),
    )
    op.create_index(
        "ix_traffic_hourly_assignment_bucket",
        "traffic_hourly",
        ["assignment_id", "hour_bucket"],
    )
    op.create_index(
        "ix_traffic_hourly_node_bucket",
        "traffic_hourly",
        ["node_id", "hour_bucket"],
    )
    op.create_index(
        "ix_traffic_hourly_hour_bucket",
        "traffic_hourly",
        ["hour_bucket"],
    )

    op.create_table(
        "traffic_rollup_state",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("hourly_watermark", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_traffic_rollup_state"),
    )


def downgrade() -> None:
    op.drop_table("traffic_rollup_state")
    op.drop_index("ix_traffic_hourly_hour_bucket", table_name="traffic_hourly")
    op.drop_index("ix_traffic_hourly_node_bucket", table_name="traffic_hourly")
    op.drop_index("ix_traffic_hourly_assignment_bucket", table_name="traffic_hourly")
    op.drop_table("traffic_hourly")
