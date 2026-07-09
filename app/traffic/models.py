from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IntPrimaryKeyMixin


class TrafficRecord(IntPrimaryKeyMixin, Base):
    __tablename__ = "traffic_records"

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("client_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    upload_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    download_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "assignment_id", "collected_at", name="uq_traffic_records_assignment_collected"
        ),
        Index("ix_traffic_records_assignment_id", "assignment_id"),
        Index("ix_traffic_records_node_id", "node_id"),
        Index("ix_traffic_records_collected_at", "collected_at"),
        Index(
            "ix_traffic_records_assignment_collected",
            "assignment_id",
            text("collected_at DESC"),
        ),
        Index(
            "ix_traffic_records_node_collected",
            "node_id",
            text("collected_at DESC"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<TrafficRecord id={self.id} assignment={self.assignment_id} "
            f"total={self.total_bytes} at={self.collected_at}>"
        )


class TrafficHourly(IntPrimaryKeyMixin, Base):
    """Hourly rollup of traffic_records. One row per (assignment, closed hour
    bucket); the raw per-sample rows that feed it can be purged sooner while
    analytics reads hit this small aggregate table instead of scanning the raw
    log. node_id is denormalised from the raw record so node-level reads avoid a
    join back through client_assignments for the node.

    Only CLOSED hour buckets are rolled up (bucket strictly before the current
    hour). The rollup job upserts each bucket with the freshly recomputed SUM
    (ON CONFLICT DO UPDATE SET = value, not +=), so re-running the job is
    idempotent and never double-counts."""

    __tablename__ = "traffic_hourly"

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("client_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    hour_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    upload_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    download_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "assignment_id", "hour_bucket", name="uq_traffic_hourly_assignment_bucket"
        ),
        Index("ix_traffic_hourly_assignment_bucket", "assignment_id", "hour_bucket"),
        Index("ix_traffic_hourly_node_bucket", "node_id", "hour_bucket"),
        Index("ix_traffic_hourly_hour_bucket", "hour_bucket"),
    )

    def __repr__(self) -> str:
        return (
            f"<TrafficHourly id={self.id} assignment={self.assignment_id} "
            f"total={self.total_bytes} bucket={self.hour_bucket}>"
        )


class TrafficRollupState(Base):
    """Single-row watermark for the hourly rollup job. `hourly_watermark` is the
    first hour bucket NOT yet aggregated; the job aggregates closed buckets from
    the watermark up to (but excluding) the current hour, then advances it. Kept
    as its own table (rather than a config value) so the watermark survives
    restarts and is shared across workers under the leader gate."""

    __tablename__ = "traffic_rollup_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    hourly_watermark: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProcessedBatch(IntPrimaryKeyMixin, Base):
    """Idempotency ledger for traffic batches. The agent resends a batch with a
    deterministic batch_id on retry; recording (node_id, batch_id) with a unique
    constraint lets a resent or concurrently-duplicated batch be detected and
    skipped instead of double-counting usage deltas."""

    __tablename__ = "processed_batches"

    node_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    batch_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("node_id", "batch_id", name="uq_processed_batches_node_batch"),
        Index("ix_processed_batches_created_at", "created_at"),
    )
