from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from app.domain.profile import SLUG_PATTERN
from app.protocols import PROTOCOLS as _PROTOCOL_SPECS
from app.providers.base.models import ProviderKind
from app.schemas.base import APIModel, InputModel

NAME_MAX_LEN = 255
PROTOCOL_MAX_LEN = 64

VALID_PROTOCOLS = frozenset(
    spec.name for spec in _PROTOCOL_SPECS if spec.providers
)


class _ProtocolValidatorMixin:
    @field_validator("protocol")
    @classmethod
    def _validate_protocol(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v.lower() not in VALID_PROTOCOLS:
            raise ValueError(
                f"Unknown protocol '{v}'. Must be one of: {', '.join(sorted(VALID_PROTOCOLS))}"
            )
        return v.lower()


class ProfileCreate(_ProtocolValidatorMixin, InputModel):
    name: str = Field(min_length=1, max_length=NAME_MAX_LEN)
    slug: str = Field(pattern=SLUG_PATTERN, max_length=64)
    provider_kind: ProviderKind
    node_id: uuid.UUID
    protocol: str = Field(min_length=1, max_length=PROTOCOL_MAX_LEN)
    settings: dict[str, Any] = Field(default_factory=dict)


class ProfileUpdate(_ProtocolValidatorMixin, InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LEN)
    protocol: str | None = Field(default=None, min_length=1, max_length=PROTOCOL_MAX_LEN)
    settings: dict[str, Any] | None = Field(default=None)
    is_active: bool | None = Field(default=None)
    expected_version: int | None = Field(default=None, ge=1)


class ProfileRead(APIModel):
    id: uuid.UUID
    name: str
    slug: str
    provider_kind: ProviderKind
    node_id: uuid.UUID
    protocol: str
    settings: dict[str, Any]
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime
