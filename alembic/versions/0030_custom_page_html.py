from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_custom_page_html"
down_revision: str = "0029_user_totp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("custom_page_html", sa.Text(), server_default="", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "custom_page_html")
