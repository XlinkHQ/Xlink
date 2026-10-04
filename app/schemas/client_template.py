from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.base import APIModel, InputModel

TemplateFormat = Literal["clash", "mihomo", "singbox"]


class ClientTemplateCreate(InputModel):
    name: str = Field(min_length=1, max_length=64)
    format: TemplateFormat
    content: str = Field(min_length=2)
    is_default: bool = False


class ClientTemplateUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    content: str | None = Field(default=None, min_length=2)
    is_default: bool | None = None


class ClientTemplateRead(APIModel):
    id: uuid.UUID
    name: str
    format: str
    content: str
    is_default: bool
    created_at: datetime
    updated_at: datetime
