from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047_user_suspended_by_owner"
down_revision = "0046_user_sessions_revoked"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Marks a user disabled specifically by an owner-suspend cascade, so restoring
    # the owner re-enables ONLY those and never clobbers an admin's manual disable.
    op.add_column(
        "users",
        sa.Column(
            "suspended_by_owner",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "suspended_by_owner")
