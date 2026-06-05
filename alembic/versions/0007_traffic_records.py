from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_traffic_records"
down_revision: str | None = "0006_gitops_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "traffic_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("upload_bytes", sa.BigInteger(), nullable=False),
        sa.Column("download_bytes", sa.BigInteger(), nullable=False),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["client_assignments.id"],
            name="fk_traffic_records_assignment_id_client_assignments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["nodes.id"],
            name="fk_traffic_records_node_id_nodes",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_traffic_records"),
        sa.UniqueConstraint(
            "assignment_id", "collected_at", name="uq_traffic_records_assignment_collected"
        ),
    )
    op.create_index("ix_traffic_records_assignment_id", "traffic_records", ["assignment_id"])
    op.create_index("ix_traffic_records_node_id", "traffic_records", ["node_id"])
    op.create_index("ix_traffic_records_collected_at", "traffic_records", ["collected_at"])
    op.create_index(
        "ix_traffic_records_assignment_collected",
        "traffic_records",
        ["assignment_id", sa.text("collected_at DESC")],
    )
    op.create_index(
        "ix_traffic_records_node_collected",
        "traffic_records",
        ["node_id", sa.text("collected_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_traffic_records_node_collected", table_name="traffic_records")
    op.drop_index("ix_traffic_records_assignment_collected", table_name="traffic_records")
    op.drop_index("ix_traffic_records_collected_at", table_name="traffic_records")
    op.drop_index("ix_traffic_records_node_id", table_name="traffic_records")
    op.drop_index("ix_traffic_records_assignment_id", table_name="traffic_records")
    op.drop_table("traffic_records")
