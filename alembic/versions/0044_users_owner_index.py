from __future__ import annotations

from alembic import op

revision = "0044_users_owner_index"
down_revision = "0043_routing_outbound_width"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # CONCURRENTLY avoids locking writes to a populated users table during
        # the build; it cannot run inside a transaction, so use autocommit.
        with op.get_context().autocommit_block():
            op.create_index(
                "ix_users_owner_removed",
                "users",
                ["owner_id", "removed"],
                unique=False,
                postgresql_concurrently=True,
                if_not_exists=True,
            )
    else:
        op.create_index(
            "ix_users_owner_removed", "users", ["owner_id", "removed"], unique=False
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.drop_index(
                "ix_users_owner_removed",
                table_name="users",
                postgresql_concurrently=True,
                if_exists=True,
            )
    else:
        op.drop_index("ix_users_owner_removed", table_name="users")
