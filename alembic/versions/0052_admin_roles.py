"""admin roles (RBAC)

Revision ID: 0052_admin_roles
Revises: 0051_user_partial_unique
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0052_admin_roles"
down_revision: str = "0051_user_partial_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json() -> sa.types.TypeEngine:
    return postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "admin_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=False, server_default=""),
        sa.Column("permissions", _json(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("limits", _json(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_admin_roles_name"),
    )
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("admin_role_id", postgresql.UUID(as_uuid=True), nullable=True))
        batch.create_foreign_key(
            "fk_users_admin_role_id", "admin_roles", ["admin_role_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index("ix_users_admin_role_id", ["admin_role_id"])


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_admin_role_id")
        batch.drop_constraint("fk_users_admin_role_id", type_="foreignkey")
        batch.drop_column("admin_role_id")
    op.drop_table("admin_roles")
