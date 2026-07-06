from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Enum, Float, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.domain.client_assignment import ClientAssignment
    from app.domain.profile import Profile

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

SLUG_PATTERN = r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$"

_JSON_VARIANT = JSONB().with_variant(JSON(), "sqlite")


class NodeStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    OFFLINE = "offline"


class Node(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "nodes"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[NodeStatus] = mapped_column(
        Enum(NodeStatus, name="node_status", native_enum=False, length=16),
        default=NodeStatus.OFFLINE,
        nullable=False,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    max_users: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    current_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    usage_coefficient: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    socks_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    socks_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    socks_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    socks_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    node_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", _JSON_VARIANT, default=dict, nullable=False
    )

    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    assignments: Mapped[list[ClientAssignment]] = relationship(back_populates="node", lazy="noload")
    profiles: Mapped[list[Profile]] = relationship(back_populates="node", lazy="noload")

    __mapper_args__: ClassVar[dict[str, Any]] = {"version_id_col": version}

    __table_args__ = (
        Index("ix_nodes_host", "host"),
        Index("ix_nodes_status", "status"),
        Index("ix_nodes_last_seen_at", "last_seen_at"),
        Index("ix_nodes_created_at_id", text("created_at DESC"), text("id DESC")),
        Index("ix_nodes_status_created_id", "status", text("created_at DESC"), text("id DESC")),
    )

    def __repr__(self) -> str:
        return f"<Node id={self.id} slug={self.slug!r} status={self.status}>"
