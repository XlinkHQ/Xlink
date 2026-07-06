from __future__ import annotations

import json

from app.core.exceptions import ValidationError
from app.domain.app_settings import AppSettings
from app.repositories.app_settings import AppSettingsRepository
from app.schemas.settings import (
    NotificationSettingsUpdate,
    SubscriptionSettingsUpdate,
    WarpSettingsUpdate,
)

CORE_KINDS = ("xray", "sing-box", "hysteria", "wireguard")


class SettingsService:
    def __init__(self, repo: AppSettingsRepository) -> None:
        self._repo = repo

    async def get_subscription(self) -> AppSettings:
        return await self._repo.get_or_create()

    async def get_core_templates(self) -> dict[str, str]:
        row = await self._repo.get_or_create()
        try:
            stored = json.loads(row.xray_core_template or "{}")
        except ValueError:
            stored = {}
        if not isinstance(stored, dict):
            stored = {}
        return {core: json.dumps(stored.get(core, {}), indent=2) for core in CORE_KINDS}

    async def update_core_template(self, core: str, template: str) -> dict[str, str]:
        if core not in CORE_KINDS:
            raise ValidationError(f"Unknown core '{core}'.", code="unknown_core")
        try:
            parsed = json.loads(template or "{}")
        except ValueError as exc:
            raise ValidationError("Core template is not valid JSON.", code="invalid_json") from exc
        if not isinstance(parsed, dict):
            raise ValidationError("Core template must be a JSON object.", code="invalid_json")
        row = await self._repo.get_or_create()
        try:
            stored = json.loads(row.xray_core_template or "{}")
        except ValueError:
            stored = {}
        if not isinstance(stored, dict):
            stored = {}
        stored[core] = parsed
        row.xray_core_template = json.dumps(stored)
        await self._repo.session.flush()
        return await self.get_core_templates()

    async def get_notifications(self) -> AppSettings:
        return await self._repo.get_or_create()

    async def update_notifications(self, data: NotificationSettingsUpdate) -> AppSettings:
        row = await self._repo.get_or_create()
        for field in (
            "notify_enabled",
            "notify_expiring_days",
            "notify_usage_percent",
            "notify_node_down",
            "webhook_address",
            "discord_webhook_url",
            "telegram_bot_token",
            "telegram_chat_ids",
        ):
            value = getattr(data, field)
            if value is not None:
                setattr(row, field, value)
        await self._repo.session.flush()
        return row

    async def get_warp(self) -> AppSettings:
        return await self._repo.get_or_create()

    async def update_warp(self, data: WarpSettingsUpdate) -> AppSettings:
        row = await self._repo.get_or_create()
        for field in (
            "warp_enabled",
            "warp_private_key",
            "warp_public_key",
            "warp_address",
            "warp_endpoint",
            "warp_reserved",
        ):
            value = getattr(data, field)
            if value is not None:
                setattr(row, field, value)
        await self._repo.session.flush()
        return row

    async def update_subscription(self, data: SubscriptionSettingsUpdate) -> AppSettings:
        row = await self._repo.get_or_create()
        if data.profile_title is not None:
            row.profile_title = data.profile_title
        if data.support_link is not None:
            row.support_link = data.support_link
        if data.update_interval_hours is not None:
            row.update_interval_hours = data.update_interval_hours
        for field in (
            "active_status_text",
            "expired_status_text",
            "limited_status_text",
            "disabled_status_text",
            "onhold_status_text",
        ):
            value = getattr(data, field)
            if value is not None:
                setattr(row, field, value)
        if data.config_remark is not None:
            row.config_remark = data.config_remark
        if data.shuffle_configs is not None:
            row.shuffle_configs = data.shuffle_configs
        if data.placeholder_if_disabled is not None:
            row.placeholder_if_disabled = data.placeholder_if_disabled
        if data.placeholder_remark is not None:
            row.placeholder_remark = data.placeholder_remark
        if data.custom_page_html is not None:
            row.custom_page_html = data.custom_page_html
        if data.rules is not None:
            row.subscription_rules = json.dumps([r.model_dump(mode="json") for r in data.rules])
        await self._repo.session.flush()
        return row
