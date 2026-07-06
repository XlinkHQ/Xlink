from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.base import APIModel, InputModel


class UserTemplateRead(APIModel):
    id: uuid.UUID
    name: str
    data_limit_bytes: int | None
    expire_days: int | None
    data_reset_strategy: str
    device_limit: int | None
    username_prefix: str
    created_at: datetime


class UserTemplateCreate(InputModel):
    name: str = Field(min_length=1, max_length=128)
    data_limit_bytes: int | None = Field(default=None, ge=0)
    expire_days: int | None = Field(default=None, ge=0, le=3650)
    data_reset_strategy: str = Field(default="no_reset", max_length=16)
    device_limit: int | None = Field(default=None, ge=0)
    username_prefix: str = Field(default="", max_length=32)


class UserTemplateUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    data_limit_bytes: int | None = Field(default=None, ge=0)
    expire_days: int | None = Field(default=None, ge=0, le=3650)
    data_reset_strategy: str | None = Field(default=None, max_length=16)
    device_limit: int | None = Field(default=None, ge=0)
    username_prefix: str | None = Field(default=None, max_length=32)
