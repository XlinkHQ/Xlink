from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.domain.node import SLUG_PATTERN, NodeStatus
from app.schemas.base import APIModel, InputModel

NAME_MAX_LEN = 255
HOST_MAX_LEN = 255
PORT_MIN = 1
PORT_MAX = 65535


class NodeCreate(InputModel):
    name: str = Field(min_length=1, max_length=NAME_MAX_LEN)
    slug: str = Field(pattern=SLUG_PATTERN, max_length=64)
    host: str = Field(min_length=1, max_length=HOST_MAX_LEN)
    port: int = Field(ge=PORT_MIN, le=PORT_MAX)
    max_users: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodeUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LEN)
    host: str | None = Field(default=None, min_length=1, max_length=HOST_MAX_LEN)
    port: int | None = Field(default=None, ge=PORT_MIN, le=PORT_MAX)
    max_users: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] | None = Field(default=None)
    expected_version: int | None = Field(default=None, ge=1)


class NodeHeartbeat(InputModel):
    current_users: int = Field(ge=0)
    status: NodeStatus | None = Field(default=None)


class NodeStatusUpdate(InputModel):
    status: NodeStatus


class NodeRead(APIModel):
    id: uuid.UUID
    name: str
    slug: str
    host: str
    port: int
    status: NodeStatus
    last_seen_at: datetime | None
    max_users: int
    current_users: int
    metadata: dict[str, Any] = Field(validation_alias="node_metadata")
    version: int
    created_at: datetime
    updated_at: datetime
