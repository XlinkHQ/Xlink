from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0042_outbounds"
down_revision: str = "0041_processed_batches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbounds",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tag", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=24), nullable=False, server_default="direct"),
        sa.Column("settings", JSONB(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tag", name="uq_outbounds_tag"),
    )


def downgrade() -> None:
    op.drop_table("outbounds")
