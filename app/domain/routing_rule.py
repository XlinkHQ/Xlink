from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RoutingRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "routing_rules"

    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    # comma-separated match values; type decides how they're interpreted
    match_type: Mapped[str] = mapped_column(String(16), nullable=False, default="domain")
    match_values: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outbound: Mapped[str] = mapped_column(String(64), nullable=False, default="block")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
