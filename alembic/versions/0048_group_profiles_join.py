from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0048_group_profiles_join"
down_revision: str = "0047_user_suspended_by_owner"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _coerce_ids(raw: object) -> list[str]:
    """Normalise a group's stored profile_ids into a list of id strings,
    tolerating JSON text (SQLite) or an already-decoded list (JSONB)."""
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(x) for x in raw if x is not None]


def upgrade() -> None:
    op.create_table(
        "group_profiles",
        sa.Column("group_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", PGUUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("group_id", "profile_id"),
    )

    # Backfill the join table from the existing JSON profile_ids column. Only
    # link ids that still correspond to a real profile so a stale id in the JSON
    # blob doesn't blow up the FK insert.
    bind = op.get_bind()
    groups = bind.execute(sa.text("SELECT id, profile_ids FROM groups")).fetchall()
    valid_profiles = {
        str(row[0]) for row in bind.execute(sa.text("SELECT id FROM profiles")).fetchall()
    }
    insert_stmt = sa.text(
        "INSERT INTO group_profiles (group_id, profile_id) VALUES (:group_id, :profile_id)"
    )
    for group_id, raw_ids in groups:
        seen: set[str] = set()
        for pid in _coerce_ids(raw_ids):
            if pid in seen or pid not in valid_profiles:
                continue
            seen.add(pid)
            bind.execute(insert_stmt, {"group_id": str(group_id), "profile_id": pid})

    op.drop_column("groups", "profile_ids")


def downgrade() -> None:
    op.add_column(
        "groups",
        sa.Column(
            "profile_ids",
            JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )

    # Repopulate the JSON column from the join table.
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    rows = bind.execute(
        sa.text(
            "SELECT group_id, profile_id FROM group_profiles ORDER BY group_id, profile_id"
        )
    ).fetchall()
    by_group: dict[str, list[str]] = {}
    for group_id, profile_id in rows:
        by_group.setdefault(str(group_id), []).append(str(profile_id))
    for group_id, ids in by_group.items():
        payload = json.dumps(ids)
        if is_sqlite:
            update = sa.text("UPDATE groups SET profile_ids = :ids WHERE id = :gid")
            bind.execute(update, {"ids": payload, "gid": group_id})
        else:
            update = sa.text(
                "UPDATE groups SET profile_ids = CAST(:ids AS jsonb) WHERE id = :gid"
            )
            bind.execute(update, {"ids": payload, "gid": group_id})

    op.drop_table("group_profiles")
