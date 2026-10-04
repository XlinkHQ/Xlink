from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class InboundHost(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inbound_hosts"

    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=True
    )

    remark: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sni: Mapped[str | None] = mapped_column(String(255), nullable=True)
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    alpn: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    security: Mapped[str | None] = mapped_column(String(16), nullable=True)
    network: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fragment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    noise: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mux: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_insecure: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # {"<ASN>": ["clean IP or host", ...]}: a subscriber whose ISP is that ASN
    # gets one of these as the address instead of `address`. CDN edges that
    # are reachable differ by ISP under censorship; this picks per ISP.
    asn_addresses: Mapped[dict[str, list[str]] | None] = mapped_column(JSON, nullable=True)

    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_universal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    chain_target_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("inbound_hosts.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_inbound_hosts_profile", "profile_id"),
        Index("ix_inbound_hosts_universal", "is_universal"),
    )

    def to_override(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.remark is not None:
            out["remark"] = self.remark
        if self.address is not None:
            out["address"] = self.address
        if self.port is not None:
            out["port"] = self.port
        if self.sni is not None:
            out["sni"] = self.sni
        if self.host is not None:
            out["host"] = self.host
        if self.path is not None:
            out["path"] = self.path
        if self.alpn is not None:
            out["alpn"] = self.alpn
        if self.fingerprint is not None:
            out["fingerprint"] = self.fingerprint
        if self.security is not None:
            out["security"] = self.security
        if self.network is not None:
            out["network"] = self.network
        if self.fragment is not None:
            out["fragment"] = self.fragment
        if self.noise is not None:
            out["noise"] = self.noise
        if self.mux:
            out["mux"] = "true"
        if self.allow_insecure:
            out["allowInsecure"] = "true"
        if self.asn_addresses:
            out["asn_addresses"] = self.asn_addresses
        return out
