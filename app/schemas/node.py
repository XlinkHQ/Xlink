from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import ipaddress
import re

from pydantic import Field, field_serializer, field_validator

from app.domain.node import SLUG_PATTERN, NodeStatus
from app.schemas.base import APIModel, InputModel

NAME_MAX_LEN = 255
HOST_MAX_LEN = 255
PORT_MIN = 1
PORT_MAX = 65535

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


def _valid_host(value: str) -> str:
    v = value.strip()
    if not v:
        raise ValueError("Host is required.")
    try:
        ipaddress.ip_address(v)
        return v
    except ValueError:
        pass
    if not _HOSTNAME_RE.match(v):
        raise ValueError("Host must be a valid IP address or domain (e.g. 1.2.3.4 or node.example.com).")
    return v


class NodeCreate(InputModel):
    name: str = Field(min_length=1, max_length=NAME_MAX_LEN)
    slug: str = Field(pattern=SLUG_PATTERN, max_length=64)
    host: str = Field(min_length=1, max_length=HOST_MAX_LEN)

    @field_validator("host")
    @classmethod
    def _v_host(cls, v: str) -> str:
        return _valid_host(v)
    port: int = Field(ge=PORT_MIN, le=PORT_MAX)
    max_users: int = Field(default=100, ge=1)
    usage_coefficient: float = Field(default=1.0, gt=0, le=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodeUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LEN)
    host: str | None = Field(default=None, min_length=1, max_length=HOST_MAX_LEN)
    port: int | None = Field(default=None, ge=PORT_MIN, le=PORT_MAX)
    max_users: int | None = Field(default=None, ge=1)
    usage_coefficient: float | None = Field(default=None, gt=0, le=1000)
    metadata: dict[str, Any] | None = Field(default=None)
    socks_enabled: bool | None = Field(default=None)
    socks_address: str | None = Field(default=None, max_length=255)
    socks_username: str | None = Field(default=None, max_length=255)
    socks_password: str | None = Field(default=None, max_length=255)
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("host")
    @classmethod
    def _v_host(cls, v: str | None) -> str | None:
        return _valid_host(v) if v is not None else v


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
    usage_coefficient: float
    socks_enabled: bool
    socks_address: str | None
    socks_username: str | None
    metadata: dict[str, Any] = Field(validation_alias="node_metadata")
    version: int
    created_at: datetime
    updated_at: datetime

    @field_serializer("metadata")
    def _strip_secret_metadata(self, value: dict[str, Any]) -> dict[str, Any]:
        # agent_token_hash is server-side auth material; never expose it via the
        # API (not even to sudo — no client needs it).
        if not isinstance(value, dict):
            return value
        return {k: v for k, v in value.items() if k != "agent_token_hash"}
