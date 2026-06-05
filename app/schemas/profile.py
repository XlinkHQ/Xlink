from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.domain.profile import SLUG_PATTERN
from app.providers.base.models import ProviderKind
from app.schemas.base import APIModel, InputModel

NAME_MAX_LEN = 255
PROTOCOL_MAX_LEN = 64


class ProfileCreate(InputModel):
    name: str = Field(min_length=1, max_length=NAME_MAX_LEN)
    slug: str = Field(pattern=SLUG_PATTERN, max_length=64)
    provider_kind: ProviderKind
    node_id: uuid.UUID
    protocol: str = Field(min_length=1, max_length=PROTOCOL_MAX_LEN)
    settings: dict[str, Any] = Field(default_factory=dict)


class ProfileUpdate(InputModel):
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
