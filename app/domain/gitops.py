from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Enum, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

_JSON_VARIANT = JSONB().with_variant(JSON(), "sqlite")


class GitOpsAction(StrEnum):
    SNAPSHOT = "snapshot"
    COMMIT = "commit"
    ROLLBACK_PLAN = "rollback_plan"


class GitOpsRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "gitops_records"

    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    action: Mapped[GitOpsAction] = mapped_column(
        Enum(GitOpsAction, name="gitops_action", native_enum=False, length=32),
        nullable=False,
    )
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, default=dict, nullable=False)
    diff: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_gitops_records_entity", "entity_type", "entity_id"),
        Index("ix_gitops_records_action", "action"),
        Index("ix_gitops_records_created_at_id", text("created_at DESC"), text("id DESC")),
    )
