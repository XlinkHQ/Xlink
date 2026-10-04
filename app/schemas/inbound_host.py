from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.base import APIModel, InputModel


class InboundHostCreate(InputModel):
    profile_id: uuid.UUID | None = Field(default=None)
    remark: str = Field(default="", max_length=255)
    address: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    sni: str | None = Field(default=None, max_length=255)
    host: str | None = Field(default=None, max_length=255)
    path: str | None = Field(default=None, max_length=512)
    alpn: str | None = Field(default=None, max_length=64)
    fingerprint: str | None = Field(default=None, max_length=64)
    security: str | None = Field(default=None, max_length=16)
    network: str | None = Field(default=None, max_length=32)
    fragment: str | None = Field(default=None, max_length=255)
    noise: str | None = Field(default=None, max_length=255)
    mux: bool = Field(default=False)
    allow_insecure: bool = Field(default=False)
    asn_addresses: dict[str, list[str]] | None = None
    weight: int = Field(default=1, ge=0, le=1000)
    is_universal: bool = Field(default=False)
    is_disabled: bool = Field(default=False)
    chain_target_id: uuid.UUID | None = Field(default=None)


class InboundHostUpdate(InputModel):
    remark: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    sni: str | None = Field(default=None, max_length=255)
    host: str | None = Field(default=None, max_length=255)
    path: str | None = Field(default=None, max_length=512)
    alpn: str | None = Field(default=None, max_length=64)
    fingerprint: str | None = Field(default=None, max_length=64)
    security: str | None = Field(default=None, max_length=16)
    network: str | None = Field(default=None, max_length=32)
    fragment: str | None = Field(default=None, max_length=255)
    noise: str | None = Field(default=None, max_length=255)
    mux: bool | None = Field(default=None)
    allow_insecure: bool | None = Field(default=None)
    asn_addresses: dict[str, list[str]] | None = None
    weight: int | None = Field(default=None, ge=0, le=1000)
    is_universal: bool | None = Field(default=None)
    is_disabled: bool | None = Field(default=None)
    chain_target_id: uuid.UUID | None = Field(default=None)


class InboundHostRead(APIModel):
    id: uuid.UUID
    profile_id: uuid.UUID | None
    remark: str
    address: str | None
    port: int | None
    sni: str | None
    host: str | None
    path: str | None
    alpn: str | None
    fingerprint: str | None
    security: str | None
    network: str | None
    fragment: str | None
    noise: str | None
    mux: bool
    allow_insecure: bool
    asn_addresses: dict[str, list[str]] | None = None
    weight: int
    is_universal: bool
    is_disabled: bool
    chain_target_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


def validate_asn_addresses(value: dict[str, list[str]] | None) -> dict[str, list[str]] | None:
    """ASN keys are numbers (an optional "AS" prefix is stripped); values are
    1-16 IPs or hostnames each. Empty maps collapse to None."""
    import ipaddress
    import re

    from app.core.exceptions import ValidationError

    if not value:
        return None
    host_re = re.compile(
        r"^(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
    )
    out: dict[str, list[str]] = {}
    if len(value) > 200:
        raise ValidationError("At most 200 ASNs per host.", code="asn_addresses_invalid")
    for raw_asn, addrs in value.items():
        asn = str(raw_asn).strip().upper().removeprefix("AS")
        if not asn.isdigit() or not 0 < int(asn) < 2**32:
            raise ValidationError(f"Bad ASN {raw_asn!r}.", code="asn_addresses_invalid")
        clean = []
        for a in addrs or []:
            a = str(a).strip()
            try:
                ipaddress.ip_address(a)
            except ValueError:
                if not host_re.match(a):
                    raise ValidationError(
                        f"Bad address {a!r} for AS{asn}.", code="asn_addresses_invalid"
                    ) from None
            clean.append(a)
        if not 0 < len(clean) <= 16:
            raise ValidationError(
                f"AS{asn} needs 1-16 addresses.", code="asn_addresses_invalid"
            )
        out[str(int(asn))] = clean
    return out
