from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FeedScope(StrEnum):
    ASSIGNMENT = "assignment"
    PROFILE = "profile"
    USER = "user"


class RenderVersion(StrEnum):
    V1 = "v1"


class SubscriptionFormat(StrEnum):
    TEXT = "text"
    BASE64 = "base64"
    XRAY_JSON = "xray_json"
    SINGBOX_JSON = "singbox_json"
    MIHOMO_YAML = "mihomo_yaml"
    CLASH_YAML = "clash_yaml"
    WIREGUARD_CONF = "wireguard_conf"
    SHADOWSOCKS_URI = "shadowsocks_uri"
    VLESS_URI = "vless_uri"
    VMESS_URI = "vmess_uri"
    TROJAN_URI = "trojan_uri"
    HYSTERIA2_URI = "hysteria2_uri"
    TUIC_URI = "tuic_uri"
    SOCKS_URI = "socks_uri"
    HTTP_URI = "http_uri"
    NAIVE_URI = "naive_uri"


class FeedRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    scope: FeedScope
    subject_id: uuid.UUID
    version: RenderVersion = RenderVersion.V1
    format: SubscriptionFormat = SubscriptionFormat.TEXT
    use_cache: bool = True

    shuffle: bool = False
    # Only the real client fetch (public subscription endpoint) may consume a
    # START_ON_FIRST_USE window — an admin/panel preview must NOT start the
    # customer's expiry clock just by reading the feed.
    activate_first_use: bool = False


class ConfigRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    assignment_id: uuid.UUID
    provider: str
    protocol: str
    uri: str
    expires_at: datetime | None = None


class FeedRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str
    version: RenderVersion
    content_hash: str = Field(min_length=64, max_length=64)
    etag: str
    expires_at: datetime | None
    items: tuple[ConfigRead, ...]
