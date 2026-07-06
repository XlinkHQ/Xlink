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
    weight: int
    is_universal: bool
    is_disabled: bool
    chain_target_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
