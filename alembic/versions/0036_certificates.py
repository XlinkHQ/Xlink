from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_certificates"
down_revision: str = "0035_notification_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "certificates",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("cert_pem", sa.Text(), nullable=False, server_default=""),
        sa.Column("key_pem", sa.Text(), nullable=False, server_default=""),
        sa.Column("issuer", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("renewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_certificates_domain", "certificates", ["domain"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_certificates_domain", table_name="certificates")
    op.drop_table("certificates")
