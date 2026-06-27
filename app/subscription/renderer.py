from __future__ import annotations

import hashlib
from datetime import datetime

from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.subscription.formats.base import FormatRenderError
from app.subscription.formats.registry import RendererRegistry, default_registry
from app.subscription.formats.uri import render_uri
from app.subscription.models import ProviderConfig, RenderedConfig, RenderedFeed
from app.subscription.schemas import RenderVersion, SubscriptionFormat

logger = get_logger("xlink.subscription")


class SubscriptionRenderer:
    def __init__(self, registry: RendererRegistry | None = None) -> None:
        self._registry = registry or default_registry()

    @property
    def registry(self) -> RendererRegistry:
        return self._registry

    def render_config(
        self,
        config: ProviderConfig,
        *,
        version: RenderVersion = RenderVersion.V1,
    ) -> RenderedConfig:
        self._check_version(version)
        return RenderedConfig(config=config, uri=render_uri(config), version=version.value)

    def render_feed(
        self,
        configs: tuple[ProviderConfig, ...],
        *,
        version: RenderVersion = RenderVersion.V1,
        feed_format: SubscriptionFormat = SubscriptionFormat.TEXT,
    ) -> RenderedFeed:
        self._check_version(version)
        rendered_list = []
        for config in configs:
            try:
                rendered_list.append(self.render_config(config, version=version))
            except FormatRenderError as exc:
                logger.warning(
                    "config_skipped",
                    protocol=config.protocol,
                    reason=str(exc),
                )
        rendered = tuple(rendered_list)
        content = self._registry.render(feed_format, tuple(r.config for r in rendered))
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return RenderedFeed(
            configs=rendered,
            content=content,
            version=version.value,
            content_hash=content_hash,
            etag=f'"{content_hash}"',
            expires_at=self._feed_expires_at(configs),
        )

    def _check_version(self, version: RenderVersion) -> None:
        if version is not RenderVersion.V1:
            raise ValidationError(
                "Unsupported subscription render version.",
                code="subscription_render_version_unsupported",
            )

    def _feed_expires_at(self, configs: tuple[ProviderConfig, ...]) -> datetime | None:
        expirations = [config.expires_at for config in configs if config.expires_at is not None]
        return min(expirations) if expirations else None
