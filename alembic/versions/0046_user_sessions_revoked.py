from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0046_user_sessions_revoked"
down_revision = "0045_command_lease_count"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("sessions_revoked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "sessions_revoked_at")
