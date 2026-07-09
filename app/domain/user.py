from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.domain.client_assignment import ClientAssignment
    from app.domain.group import Group
    from app.domain.refresh_token import RefreshToken

_JSON_VARIANT = JSONB().with_variant(JSON(), "sqlite")

admin_groups = Table(
    "admin_groups",
    Base.metadata,
    Column(
        "admin_id",
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "group_id",
        PGUUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class DataResetStrategy(StrEnum):
    NO_RESET = "no_reset"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class UserExpireStrategy(StrEnum):
    NEVER = "never"
    FIXED_DATE = "fixed_date"
    START_ON_FIRST_USE = "start_on_first_use"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # Uniqueness is enforced by PARTIAL unique indexes (WHERE removed = false),
    # declared in __table_args__ — NOT plain column uniqueness. A soft-deleted
    # user (removed = true) frees its username/email for reuse by a live user,
    # while two LIVE users still cannot collide.
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False, length=16),
        default=UserRole.USER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # True only while disabled by an owner-suspend cascade; lets restore re-enable
    # exactly these users without clobbering an admin's manual disable.
    suspended_by_owner: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=text("false")
    )

    data_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sub_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    sub_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sub_last_user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sessions_revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    data_reset_strategy: Mapped[DataResetStrategy] = mapped_column(
        Enum(
            DataResetStrategy,
            name="data_reset_strategy",
            native_enum=False,
            length=16,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=DataResetStrategy.NO_RESET,
        nullable=False,
    )
    last_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    on_hold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    on_hold_duration_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    expire_strategy: Mapped[UserExpireStrategy] = mapped_column(
        Enum(
            UserExpireStrategy,
            name="user_expire_strategy",
            native_enum=False,
            length=24,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=UserExpireStrategy.NEVER,
        nullable=False,
    )

    activation_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    removed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    device_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    pinned_node_ids: Mapped[list[Any]] = mapped_column(_JSON_VARIANT, default=list, nullable=False)

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    is_sudo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    all_groups_access: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    modify_users_access: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    subscription_url_prefix: Mapped[str | None] = mapped_column(String(512), nullable=True)

    admin_user_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    admin_traffic_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    users_data_usage: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    scoped_groups: Mapped[list[Group]] = relationship(
        "Group", secondary=admin_groups, lazy="noload"
    )

    assignments: Mapped[list[ClientAssignment]] = relationship(
        back_populates="user", lazy="noload"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="user", lazy="noload")

    __table_args__ = (
        # Partial unique indexes: uniqueness applies only to live (non-removed)
        # rows so a soft-deleted user's username/email can be reused. Named to
        # match the old constraints so IntegrityError-detail conflict mapping
        # (repositories/user.py::_conflict_from_integrity) still resolves.
        Index(
            "uq_users_username",
            "username",
            unique=True,
            postgresql_where=text("removed = false"),
            sqlite_where=text("removed = 0"),
        ),
        Index(
            "uq_users_email",
            "email",
            unique=True,
            postgresql_where=text("removed = false"),
            sqlite_where=text("removed = 0"),
        ),
        Index("ix_users_email_active", "email", "is_active"),
        Index("ix_users_role", "role"),
        Index("ix_users_removed", "removed"),
        Index("ix_users_created_at_id", text("created_at DESC"), text("id DESC")),
        Index(
            "ix_users_role_active_created_id",
            "role",
            "is_active",
            text("created_at DESC"),
            text("id DESC"),
        ),
    )

    @property
    def is_admin(self) -> bool:
        return self.role is UserRole.ADMIN

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
