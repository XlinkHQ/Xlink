from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_admin_quotas"
down_revision: str = "0036_certificates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("admin_user_limit", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("admin_traffic_limit_bytes", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "admin_traffic_limit_bytes")
    op.drop_column("users", "admin_user_limit")
