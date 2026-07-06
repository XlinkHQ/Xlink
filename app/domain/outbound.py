from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

_JSON_VARIANT = JSON().with_variant(JSONB(), "postgresql")


class Outbound(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outbounds"

    tag: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(24), nullable=False, default="direct")
    settings: Mapped[dict[str, Any]] = mapped_column(_JSON_VARIANT, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
