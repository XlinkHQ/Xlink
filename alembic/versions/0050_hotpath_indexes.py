from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0050_hotpath_indexes"
down_revision: str = "0049_traffic_hourly_rollup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # 1) Composite (user_id, status) on client_assignments.
    #    Serves the active-assignment / subscription lookup:
    #      - app/repositories/client_assignment.py::list_keyset filters
    #        `user_id == ...` AND `status == ...` together (leading col user_id).
    #      - app/subscription/repository.py::list_user_sources filters
    #        `user_id == ...` (uses the leading column), then the generator drops
    #        non-ACTIVE rows (app/subscription/generator.py ~248). The composite
    #        lets the ACTIVE filter be index-covered instead of a Python scan.
    #    The existing single-column ix_client_assignments_user_id is now
    #    redundant for these paths but is left in place (other code filters
    #    user_id alone and dropping it is out of scope for this change).
    op.create_index(
        "ix_client_assignments_user_status",
        "client_assignments",
        ["user_id", "status"],
        unique=False,
    )

    # 2) audit-by-actor. The real query
    #    (app/api/v1/routers/audit.py::_audit_query) filters
    #    `actor_username ILIKE '%needle%'` — a LEADING-wildcard substring match.
    #    A btree index cannot serve a leading '%...%' (it can only anchor a
    #    left-prefix), so a btree on actor_username would be dead weight. On
    #    Postgres a pg_trgm GIN index DOES accelerate this substring/ILIKE scan;
    #    add it there. SQLite has no pg_trgm, so skip it (the test DB is small and
    #    falls back to a table scan, which is fine) — this keeps the SQLite
    #    upgrade path working.
    if is_pg:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.create_index(
            "ix_audit_log_actor_username_trgm",
            "audit_log",
            ["actor_username"],
            unique=False,
            postgresql_using="gin",
            postgresql_ops={"actor_username": "gin_trgm_ops"},
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.drop_index("ix_audit_log_actor_username_trgm", table_name="audit_log")
    op.drop_index("ix_client_assignments_user_status", table_name="client_assignments")
