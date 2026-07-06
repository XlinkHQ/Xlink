from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_processed_batches"
down_revision: str = "0040_node_socks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "processed_batches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("node_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("node_id", "batch_id", name="uq_processed_batches_node_batch"),
    )
    op.create_index("ix_processed_batches_created_at", "processed_batches", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_processed_batches_created_at", table_name="processed_batches")
    op.drop_table("processed_batches")
