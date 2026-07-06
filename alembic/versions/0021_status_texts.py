from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_status_texts"
down_revision: str = "0020_user_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = {
    "active_status_text": "Active",
    "expired_status_text": "Expired",
    "limited_status_text": "Limited",
    "disabled_status_text": "Disabled",
    "onhold_status_text": "On-Hold",
}


def upgrade() -> None:
    for name, default in _COLUMNS.items():
        op.add_column(
            "app_settings",
            sa.Column(name, sa.String(length=64), nullable=False, server_default=default),
        )


def downgrade() -> None:
    for name in _COLUMNS:
        op.drop_column("app_settings", name)
