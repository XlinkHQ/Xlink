from __future__ import annotations

from typing import Any, ClassVar

from sqlalchemy import JSON, BigInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

SLUG_PATTERN = r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$"
_JSON_VARIANT = JSONB().with_variant(JSON(), "sqlite")


class Group(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "groups"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    profile_ids: Mapped[list[Any]] = mapped_column(_JSON_VARIANT, default=list, nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    __mapper_args__: ClassVar[dict[str, Any]] = {"version_id_col": version}
