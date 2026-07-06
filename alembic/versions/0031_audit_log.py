from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0031_audit_log"
down_revision: str = "0030_custom_page_html"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column("actor_username", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("status_code", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ip_address", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_table("audit_log")
