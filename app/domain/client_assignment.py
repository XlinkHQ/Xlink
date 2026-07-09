from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.providers.base.models import ProviderKind

if TYPE_CHECKING:
    from app.domain.node import Node
    from app.domain.profile import Profile
    from app.domain.user import User

_JSON_VARIANT = JSONB().with_variant(JSON(), "sqlite")


class AssignmentStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    EXPIRED = "expired"
    LIMITED = "limited"


class ClientAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "client_assignments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_kind: Mapped[ProviderKind] = mapped_column(
        Enum(ProviderKind, name="provider_kind", native_enum=False, length=32),
        nullable=False,
    )
    provider_client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[AssignmentStatus] = mapped_column(
        Enum(AssignmentStatus, name="assignment_status", native_enum=False, length=16),
        default=AssignmentStatus.ACTIVE,
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    traffic_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    credentials: Mapped[dict[str, Any]] = mapped_column(
        _JSON_VARIANT, default=dict, server_default=text("'{}'"), nullable=False
    )

    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    user: Mapped[User] = relationship(back_populates="assignments", lazy="noload")
    profile: Mapped[Profile] = relationship(back_populates="assignments", lazy="noload")
    node: Mapped[Node] = relationship(back_populates="assignments", lazy="noload")

    __mapper_args__: ClassVar[dict[str, Any]] = {"version_id_col": version}

    __table_args__ = (
        UniqueConstraint("user_id", "profile_id", "node_id", name="uq_client_assignments_triplet"),
        Index("ix_client_assignments_user_id", "user_id"),
        Index("ix_client_assignments_profile_id", "profile_id"),
        Index("ix_client_assignments_node_id", "node_id"),
        Index("ix_client_assignments_provider_kind", "provider_kind"),
        Index("ix_client_assignments_status", "status"),
        # Composite for the active-assignment / subscription lookup that filters
        # user_id (+ status): repositories.client_assignment.list_keyset and
        # subscription.repository.list_user_sources (see migration 0050).
        Index("ix_client_assignments_user_status", "user_id", "status"),
        Index("ix_client_assignments_expires_at", "expires_at"),
        Index(
            "ix_client_assignments_created_at_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
    )

    def __repr__(self) -> str:
        return f"<ClientAssignment id={self.id} user={self.user_id} profile={self.profile_id}>"
