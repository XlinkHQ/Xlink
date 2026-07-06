from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043_routing_outbound_width"
down_revision: str = "0042_outbounds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "routing_rules", "outbound", type_=sa.String(length=64), existing_nullable=False
    )


def downgrade() -> None:
    op.alter_column(
        "routing_rules", "outbound", type_=sa.String(length=16), existing_nullable=False
    )
