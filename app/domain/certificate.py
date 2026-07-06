from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CertificateSource(StrEnum):
    MANUAL = "manual"
    ACME = "acme"


class CertificateStatus(StrEnum):
    ACTIVE = "active"
    PENDING = "pending"
    ERROR = "error"


class Certificate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "certificates"

    domain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    source: Mapped[CertificateSource] = mapped_column(
        String(16), nullable=False, default=CertificateSource.MANUAL
    )
    status: Mapped[CertificateStatus] = mapped_column(
        String(16), nullable=False, default=CertificateStatus.ACTIVE
    )
    cert_pem: Mapped[str] = mapped_column(Text, nullable=False, default="")
    key_pem: Mapped[str] = mapped_column(Text, nullable=False, default="")
    issuer: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    not_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    renewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
