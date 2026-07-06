from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_templates"

    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    data_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expire_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_reset_strategy: Mapped[str] = mapped_column(String(16), nullable=False, default="no_reset")
    device_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username_prefix: Mapped[str] = mapped_column(String(32), nullable=False, default="")
