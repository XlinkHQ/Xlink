"""client templates

Revision ID: 0053_client_templates
Revises: 0052_admin_roles
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0053_client_templates"
down_revision: str = "0052_admin_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "client_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_client_templates_name"),
    )
    op.create_index("ix_client_templates_format", "client_templates", ["format"])


def downgrade() -> None:
    op.drop_index("ix_client_templates_format", table_name="client_templates")
    op.drop_table("client_templates")
