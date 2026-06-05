from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_gitops_records"
down_revision: str | None = "0005_client_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gitops_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "action",
            sa.Enum(
                "snapshot",
                "commit",
                "rollback_plan",
                name="gitops_action",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column("message", sa.String(length=500), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("diff", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_gitops_records"),
    )
    op.create_index("ix_gitops_records_entity", "gitops_records", ["entity_type", "entity_id"])
    op.create_index("ix_gitops_records_action", "gitops_records", ["action"])
    op.create_index(
        "ix_gitops_records_created_at_id",
        "gitops_records",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_gitops_records_created_at_id", table_name="gitops_records")
    op.drop_index("ix_gitops_records_action", table_name="gitops_records")
    op.drop_index("ix_gitops_records_entity", table_name="gitops_records")
    op.drop_table("gitops_records")
