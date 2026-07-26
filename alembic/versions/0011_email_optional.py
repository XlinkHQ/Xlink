from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_email_optional"
down_revision: str = "0010_assignment_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "email", existing_type=sa.String(320), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE users SET email = '' WHERE email IS NULL")
    op.alter_column("users", "email", existing_type=sa.String(320), nullable=False)
