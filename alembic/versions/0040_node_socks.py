from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_node_socks"
down_revision: str = "0039_warp_routing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("socks_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("nodes", sa.Column("socks_address", sa.String(length=255), nullable=True))
    op.add_column("nodes", sa.Column("socks_username", sa.String(length=255), nullable=True))
    op.add_column("nodes", sa.Column("socks_password", sa.String(length=255), nullable=True))


def downgrade() -> None:
    for col in ("socks_password", "socks_username", "socks_address", "socks_enabled"):
        op.drop_column("nodes", col)
