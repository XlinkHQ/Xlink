from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0051_user_partial_unique"
down_revision: str = "0050_hotpath_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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

    dedup = (
        "UPDATE users SET {col} = {col} || '#deleted-' || id::text "
        "WHERE removed = true AND {col} IN "
        "(SELECT {col} FROM users WHERE removed = false)"
    )
    if dialect == "postgresql":
        op.execute(dedup.format(col="username"))
        op.execute(dedup.format(col="email"))
        op.drop_index("uq_users_username", table_name="users")
        op.drop_index("uq_users_email", table_name="users")
        op.create_unique_constraint("uq_users_username", "users", ["username"])
        op.create_unique_constraint("uq_users_email", "users", ["email"])
    else:
        op.execute("DROP INDEX IF EXISTS uq_users_username")
        op.execute("DROP INDEX IF EXISTS uq_users_email")
        op.create_index("uq_users_username", "users", ["username"], unique=True)
        op.create_index("uq_users_email", "users", ["email"], unique=True)
