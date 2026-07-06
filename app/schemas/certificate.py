from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.base import APIModel, InputModel

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


def _valid_domain(v: str) -> str:
    v = v.strip()
    if not _DOMAIN_RE.match(v):
        raise ValueError("Domain must be a valid hostname (e.g. sub.example.com).")
    return v


class CertificateRead(APIModel):
    id: uuid.UUID
    domain: str
    source: str
    status: str
    issuer: str
    not_before: datetime | None
    not_after: datetime | None
    last_error: str
    renewed_at: datetime | None
    created_at: datetime


class CertificateImport(InputModel):
    domain: str = Field(min_length=1, max_length=255)
    cert_pem: str = Field(min_length=1, max_length=100000)
    key_pem: str = Field(min_length=1, max_length=100000)

    @field_validator("domain")
    @classmethod
    def _v_domain(cls, v: str) -> str:
        return _valid_domain(v)


class CertificateAcmeRequest(InputModel):
    domain: str = Field(min_length=1, max_length=255)

    @field_validator("domain")
    @classmethod
    def _v_domain(cls, v: str) -> str:
        return _valid_domain(v)
