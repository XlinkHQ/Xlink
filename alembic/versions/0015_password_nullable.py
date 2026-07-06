from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_password_nullable"
down_revision: str = "0014_app_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "hashed_password", existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE users SET hashed_password = '' WHERE hashed_password IS NULL")
    op.alter_column("users", "hashed_password", existing_type=sa.String(length=255), nullable=False)
