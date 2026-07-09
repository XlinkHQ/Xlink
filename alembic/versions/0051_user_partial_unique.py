from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0051_user_partial_unique"
down_revision: str = "0050_hotpath_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Soft-deleted users (removed = true) keep their row, so a PLAIN unique
    # constraint on username/email permanently reserves those values against a
    # tombstone. Replace the plain constraints with PARTIAL unique indexes that
    # only cover live rows (WHERE removed = false): a deleted user's
    # username/email becomes reusable, while two LIVE users still can't collide.
    #
    # The partial indexes reuse the old constraint names so the IntegrityError
    # detail still contains "uq_users_username" / "uq_users_email" and the
    # conflict-message mapping in repositories/user.py keeps working.
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.drop_constraint("uq_users_username", "users", type_="unique")
        op.drop_constraint("uq_users_email", "users", type_="unique")
        op.create_index(
            "uq_users_username",
            "users",
            ["username"],
            unique=True,
            postgresql_where="removed = false",
        )
        op.create_index(
            "uq_users_email",
            "users",
            ["email"],
            unique=True,
            postgresql_where="removed = false",
        )
    else:
        # SQLite (test DB). SQLite cannot ALTER TABLE ... DROP CONSTRAINT, but it
        # DOES support partial indexes. Drop the old unique constraints/indexes
        # by name if present (they may be table-level constraints created by
        # create_all rather than the migration), then create the partial ones.
        # Both statements are IF EXISTS so this path is safe whether the base
        # schema came from this migration chain or from Base.metadata.create_all.
        op.execute("DROP INDEX IF EXISTS uq_users_username")
        op.execute("DROP INDEX IF EXISTS uq_users_email")
        op.create_index(
            "uq_users_username",
            "users",
            ["username"],
            unique=True,
            sqlite_where="removed = 0",
        )
        op.create_index(
            "uq_users_email",
            "users",
            ["email"],
            unique=True,
            sqlite_where="removed = 0",
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.drop_index("uq_users_username", table_name="users")
        op.drop_index("uq_users_email", table_name="users")
        op.create_unique_constraint("uq_users_username", "users", ["username"])
        op.create_unique_constraint("uq_users_email", "users", ["email"])
    else:
        op.execute("DROP INDEX IF EXISTS uq_users_username")
        op.execute("DROP INDEX IF EXISTS uq_users_email")
        # Restore plain (full) unique indexes under the same names on SQLite.
        op.create_index("uq_users_username", "users", ["username"], unique=True)
        op.create_index("uq_users_email", "users", ["email"], unique=True)
