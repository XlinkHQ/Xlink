from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_user_quota"
down_revision: str = "0015_password_nullable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("data_limit_bytes", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("expire_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "expire_at")
    op.drop_column("users", "data_limit_bytes")
