from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_assignment_used_bytes"
down_revision: str | None = "0008_advanced_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "client_assignments",
        sa.Column("used_bytes", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.alter_column("client_assignments", "used_bytes", server_default=None)


def downgrade() -> None:
    op.drop_column("client_assignments", "used_bytes")
