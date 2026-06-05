from __future__ import annotations

import uuid
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Enum,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.providers.base.models import ProviderKind

SLUG_PATTERN = r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$"

_JSON_VARIANT = JSONB().with_variant(JSON(), "sqlite")


class Profile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "profiles"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    provider_kind: Mapped[ProviderKind] = mapped_column(
        Enum(ProviderKind, name="provider_kind", native_enum=False, length=32),
        nullable=False,
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    protocol: Mapped[str] = mapped_column(String(64), nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    __mapper_args__: ClassVar[dict[str, Any]] = {"version_id_col": version}

    __table_args__ = (
        Index("ix_profiles_provider_kind", "provider_kind"),
        Index("ix_profiles_node_id", "node_id"),
        Index("ix_profiles_is_active", "is_active"),
        Index("ix_profiles_created_at_id", text("created_at DESC"), text("id DESC")),
    )

    def __repr__(self) -> str:
        return f"<Profile id={self.id} slug={self.slug!r} kind={self.provider_kind}>"
