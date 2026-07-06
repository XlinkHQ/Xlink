from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0034_user_node_pinning"
down_revision: str = "0033_user_devices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("pinned_node_ids", JSONB(), server_default="[]", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "pinned_node_ids")
