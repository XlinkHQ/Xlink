from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0017_assignment_group"
down_revision: str = "0016_user_quota"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("client_assignments", sa.Column("group_id", PGUUID(as_uuid=True), nullable=True))
    op.create_index("ix_client_assignments_group_id", "client_assignments", ["group_id"])
    op.create_foreign_key(
        "fk_client_assignments_group",
        "client_assignments",
        "groups",
        ["group_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_client_assignments_group", "client_assignments", type_="foreignkey")
    op.drop_index("ix_client_assignments_group_id", table_name="client_assignments")
    op.drop_column("client_assignments", "group_id")
