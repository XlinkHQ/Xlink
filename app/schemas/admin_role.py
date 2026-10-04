from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.base import APIModel, InputModel


class AdminRoleCreate(InputModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=255)
    permissions: dict[str, dict[str, int]] = Field(default_factory=dict)
    limits: dict[str, int | None] = Field(default_factory=dict)


class AdminRoleUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    permissions: dict[str, dict[str, int]] | None = None
    limits: dict[str, int | None] | None = None


class AdminRoleRead(APIModel):
    id: uuid.UUID
    name: str
    description: str
    permissions: dict[str, Any]
    limits: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class RoleCatalogueRead(APIModel):
    """What a role editor can offer: resources, their actions, the scopes."""

    resources: dict[str, list[str]]
    limits: list[str]
    scopes: dict[str, int]
