from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

_JSON_VARIANT = JSONB().with_variant(JSON(), "sqlite")


class AdminRole(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named permission set assignable to non-sudo admins.

    `permissions` is `{resource: {action: scope}}` with scope 0 = denied,
    1 = only users this admin owns, 2 = all users. An action missing from the
    map is denied. `limits` bounds what the admin may grant (see app.core.rbac).
    """

    __tablename__ = "admin_roles"

    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    permissions: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False, default=dict)
    limits: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, nullable=False, default=dict)
