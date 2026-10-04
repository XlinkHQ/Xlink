"""per-ASN clean addresses on inbound hosts

Revision ID: 0055_inbound_host_asn_addresses
Revises: 0054_ss2022_server_password
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0055_inbound_host_asn_addresses"
down_revision: str = "0054_ss2022_server_password"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("inbound_hosts", sa.Column("asn_addresses", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("inbound_hosts", "asn_addresses")
