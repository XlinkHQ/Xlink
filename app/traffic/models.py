from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
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
