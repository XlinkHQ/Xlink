"""backfill shadowsocks 2022 server PSK

Multi-user 2022 inbounds need a server key; profiles saved before it was
required get one so their nodes and subscriptions start working.

Revision ID: 0054_ss2022_server_password
Revises: 0053_client_templates
"""

from __future__ import annotations

import base64
import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054_ss2022_server_password"
down_revision: str = "0053_client_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_profiles = sa.table(
    "profiles",
    sa.column("id", sa.Uuid()),
    sa.column("protocol", sa.String()),
    sa.column("settings", sa.JSON()),
)


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(_profiles.c.id, _profiles.c.protocol, _profiles.c.settings).where(
            _profiles.c.protocol.in_(("shadowsocks", "shadowsocks2022"))
        )
    ).all()
    for pid, protocol, settings in rows:
        s = dict(settings or {})
        default = "2022-blake3-aes-256-gcm" if protocol == "shadowsocks2022" else ""
        method = str(s.get("method") or default).lower()
        if not method.startswith("2022-") or s.get("serverPassword"):
            continue
        n = 16 if method == "2022-blake3-aes-128-gcm" else 32
        s["serverPassword"] = base64.b64encode(secrets.token_bytes(n)).decode()
        bind.execute(sa.update(_profiles).where(_profiles.c.id == pid).values(settings=s))


def downgrade() -> None:
    # Keeping the generated key is harmless; removing it would break nodes.
    pass
