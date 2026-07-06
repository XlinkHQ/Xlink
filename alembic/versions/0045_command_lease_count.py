from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045_command_lease_count"
down_revision = "0044_users_owner_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "node_commands",
        sa.Column("lease_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("node_commands", "lease_count")
