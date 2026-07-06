from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.domain.group import SLUG_PATTERN
from app.schemas.base import APIModel, InputModel

NAME_MAX_LEN = 255


class GroupCreate(InputModel):
    name: str = Field(min_length=1, max_length=NAME_MAX_LEN)
    slug: str = Field(pattern=SLUG_PATTERN, max_length=64)
    profile_ids: list[uuid.UUID] = Field(default_factory=list)


class GroupUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LEN)
    profile_ids: list[uuid.UUID] | None = Field(default=None)
    expected_version: int | None = Field(default=None, ge=1)


class GroupRead(APIModel):
    id: uuid.UUID
    name: str
    slug: str
    profile_ids: list[uuid.UUID]
    version: int
    created_at: datetime
    updated_at: datetime
