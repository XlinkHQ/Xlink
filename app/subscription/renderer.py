from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime

from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.subscription.formats.base import FormatRenderError
from app.subscription.formats.capabilities import supported_protocols
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
        # A protocol the requested FORMAT structurally can't carry (e.g. wireguard
        # in a clash feed, hysteria2 in xray_json) is a KNOWN skip, not an error.
        # Compute those drops up front from the single capability matrix and LOG
        # them once per feed, so the client no longer silently receives fewer
        # nodes than assigned with no signal. Genuine render errors (bad data)
        # still surface as FormatRenderError inside the renderers.
        self._log_structural_drops(configs, feed_format)
        # Build the feed body from the ORIGINAL configs, not the URI-render
        # survivors: some protocols (e.g. shadowtls) have no single-line URI form
        # yet are fully renderable by the sing-box / clash format renderers, which
        # each filter to what they support. Pre-filtering on render_uri here would
        # silently drop those from every feed. `rendered` still drives per-item
        # URI metadata below.
        content = self._registry.render(feed_format, configs)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return RenderedFeed(
            configs=rendered,
            content=content,
            version=version.value,
            content_hash=content_hash,
            etag=f'"{content_hash}"',
            expires_at=self._feed_expires_at(configs),
        )

    def _log_structural_drops(
        self,
        configs: tuple[ProviderConfig, ...],
        feed_format: SubscriptionFormat,
    ) -> None:
        allowed = supported_protocols(feed_format)
        if not allowed:
            # Format has no matrix entry (e.g. a newly-added format): stay silent
            # rather than reporting every config as dropped. The parity test
            # guards against a format ever being missing here.
            return
        dropped = Counter(c.protocol for c in configs if c.protocol not in allowed)
        if not dropped:
            return
        logger.info(
            "subscription_feed_dropped",
            format=feed_format.value,
            protocols=sorted(dropped),
            count=sum(dropped.values()),
            by_protocol=dict(sorted(dropped.items())),
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
