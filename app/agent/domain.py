from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IntPrimaryKeyMixin, TimestampMixin, UUIDPrimaryKeyMixin

_JSON_VARIANT = JSONB().with_variant(JSON(), "sqlite")


class CommandKind(StrEnum):
    APPLY_CONFIG = "apply_config"
    RELOAD = "reload"
    RESTART = "restart"
    UPGRADE = "upgrade"
    ROLLBACK = "rollback"
    UPDATE_GEO = "update_geo"
    COLLECT_DIAGNOSTICS = "collect_diagnostics"
    PROVIDER_HEALTHCHECK = "provider_healthcheck"
    REALITY_SCAN = "reality_scan"


class CommandStatus(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class DriftSeverity(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProviderHealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class NodeCommand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "node_commands"

    node_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[CommandKind] = mapped_column(
        Enum(CommandKind, name="node_command_kind", native_enum=False, length=32),
        nullable=False,
    )
    status: Mapped[CommandStatus] = mapped_column(
        Enum(CommandStatus, name="node_command_status", native_enum=False, length=16),
        default=CommandStatus.PENDING,
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, default=dict, nullable=False)
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    origin: Mapped[str] = mapped_column(String(64), nullable=False, default="self_healing")
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    lease_count: Mapped[int] = mapped_column(default=0, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(default=3, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, default=dict, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_node_commands_node_id", "node_id"),
        Index("ix_node_commands_status", "status"),
        Index("ix_node_commands_node_status", "node_id", "status"),
        Index("ix_node_commands_created_at_id", text("created_at DESC"), text("id DESC")),
    )

    def __repr__(self) -> str:
        return f"<NodeCommand id={self.id} kind={self.kind} status={self.status}>"


class NodeDriftReport(IntPrimaryKeyMixin, Base):
    __tablename__ = "node_drift_reports"

    node_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    desired_version: Mapped[str] = mapped_column(String(64), nullable=False)
    reported_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[DriftSeverity] = mapped_column(
        Enum(DriftSeverity, name="node_drift_severity", native_enum=False, length=16),
        default=DriftSeverity.NONE,
        nullable=False,
    )
    drift: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, default=dict, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    remediated: Mapped[bool] = mapped_column(default=False, nullable=False)

    __table_args__ = (
        Index("ix_node_drift_reports_node_id", "node_id"),
        Index("ix_node_drift_reports_severity", "severity"),
        Index("ix_node_drift_reports_node_detected", "node_id", text("detected_at DESC")),
    )

    def __repr__(self) -> str:
        return f"<NodeDriftReport node={self.node_id} severity={self.severity}>"


class NodeProviderHealth(IntPrimaryKeyMixin, Base):
    __tablename__ = "node_provider_health"

    node_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ProviderHealthStatus] = mapped_column(
        Enum(
            ProviderHealthStatus, name="node_provider_health_status", native_enum=False, length=16
        ),
        default=ProviderHealthStatus.UNKNOWN,
        nullable=False,
    )
    latency_ms: Mapped[float | None] = mapped_column(nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_node_provider_health_node_id", "node_id"),
        Index("ix_node_provider_health_node_provider", "node_id", "provider_name"),
        Index("ix_node_provider_health_checked", text("checked_at DESC")),
    )

    def __repr__(self) -> str:
        return f"<NodeProviderHealth provider={self.provider_name} status={self.status}>"
