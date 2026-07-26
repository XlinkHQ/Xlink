from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import APIModel, InputModel


class SubscriptionRuleResult(StrEnum):
    LINKS = "links"
    BASE64 = "base64"
    XRAY = "xray"
    SINGBOX = "singbox"
    CLASH = "clash"
    CLASH_META = "clash-meta"
    BLOCK = "block"


class SubscriptionRule(BaseModel):
    pattern: str = Field(min_length=1, max_length=256)
    result: SubscriptionRuleResult

    @field_validator("pattern")
    @classmethod
    def _valid_regex(cls, v: str) -> str:
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern: {exc}") from exc
        return v


class SubscriptionSettingsRead(APIModel):
    profile_title: str
    support_link: str
    update_interval_hours: int
    active_status_text: str
    expired_status_text: str
    limited_status_text: str
    disabled_status_text: str
    onhold_status_text: str
    config_remark: str
    shuffle_configs: bool
    placeholder_if_disabled: bool
    placeholder_remark: str
    custom_page_html: str
    rules: list[SubscriptionRule]


class WarpSettingsRead(APIModel):
    warp_enabled: bool
    warp_private_key: str
    warp_public_key: str
    warp_address: str
    warp_endpoint: str
    warp_reserved: str


class WarpSettingsUpdate(InputModel):
    warp_enabled: bool | None = Field(default=None)
    warp_private_key: str | None = Field(default=None, max_length=128)
    warp_public_key: str | None = Field(default=None, max_length=128)
    warp_address: str | None = Field(default=None, max_length=255)
    warp_endpoint: str | None = Field(default=None, max_length=255)
    warp_reserved: str | None = Field(default=None, max_length=64)


class NotificationSettingsRead(APIModel):
    notify_enabled: bool
    notify_expiring_days: int
    notify_usage_percent: int
    notify_node_down: bool
    webhook_address: str
    discord_webhook_url: str
    telegram_bot_token: str
    telegram_chat_ids: str


class NotificationSettingsUpdate(InputModel):
    notify_enabled: bool | None = Field(default=None)
    notify_expiring_days: int | None = Field(default=None, ge=0, le=365)
    notify_usage_percent: int | None = Field(default=None, ge=1, le=100)
    notify_node_down: bool | None = Field(default=None)
    webhook_address: str | None = Field(default=None, max_length=1024)
    discord_webhook_url: str | None = Field(default=None, max_length=1024)
    telegram_bot_token: str | None = Field(default=None, max_length=255)
    telegram_chat_ids: str | None = Field(default=None, max_length=1024)


class SubscriptionSettingsUpdate(InputModel):
    profile_title: str | None = Field(default=None, min_length=1, max_length=255)
    support_link: str | None = Field(default=None, max_length=512)

    @field_validator("support_link")
    @classmethod
    def _safe_support_link(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return v
        low = v.strip().lower()
        if not low.startswith(("http://", "https://", "mailto:", "tg://", "https://t.me/")):
            raise ValueError("support_link must be http(s)/mailto/tg")
        return v.strip()
    update_interval_hours: int | None = Field(default=None, ge=1, le=168)
    active_status_text: str | None = Field(default=None, min_length=1, max_length=64)
    expired_status_text: str | None = Field(default=None, min_length=1, max_length=64)
    limited_status_text: str | None = Field(default=None, min_length=1, max_length=64)
    disabled_status_text: str | None = Field(default=None, min_length=1, max_length=64)
    onhold_status_text: str | None = Field(default=None, min_length=1, max_length=64)
    config_remark: str | None = Field(default=None, max_length=255)
    shuffle_configs: bool | None = Field(default=None)
    placeholder_if_disabled: bool | None = Field(default=None)
    placeholder_remark: str | None = Field(default=None, max_length=255)
    custom_page_html: str | None = Field(default=None, max_length=100000)
    rules: list[SubscriptionRule] | None = Field(default=None, max_length=64)
