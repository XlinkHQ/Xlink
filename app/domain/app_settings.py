from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

SINGLETON_ID = 1


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SINGLETON_ID)
    profile_title: Mapped[str] = mapped_column(String(255), nullable=False, default="XLink")
    support_link: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    update_interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=12)

    active_status_text: Mapped[str] = mapped_column(String(64), nullable=False, default="Active")
    expired_status_text: Mapped[str] = mapped_column(String(64), nullable=False, default="Expired")
    limited_status_text: Mapped[str] = mapped_column(String(64), nullable=False, default="Limited")
    disabled_status_text: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Disabled"
    )
    onhold_status_text: Mapped[str] = mapped_column(String(64), nullable=False, default="On-Hold")

    config_remark: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    shuffle_configs: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    placeholder_if_disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    placeholder_remark: Mapped[str] = mapped_column(
        String(255), nullable=False, default="Subscription disabled — contact support"
    )

    subscription_rules: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    custom_page_html: Mapped[str] = mapped_column(Text, nullable=False, default="")

    xray_core_template: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    notify_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_expiring_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    notify_usage_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    notify_node_down: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    webhook_address: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    discord_webhook_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    telegram_bot_token: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    telegram_chat_ids: Mapped[str] = mapped_column(String(1024), nullable=False, default="")

    warp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    warp_private_key: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    warp_public_key: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    warp_address: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    warp_endpoint: Mapped[str] = mapped_column(
        String(255), nullable=False, default="engage.cloudflareclient.com:2408"
    )
    warp_reserved: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @property
    def rules(self) -> list[dict[str, str]]:
        try:
            parsed = json.loads(self.subscription_rules or "[]")
        except ValueError:
            return []
        return parsed if isinstance(parsed, list) else []
