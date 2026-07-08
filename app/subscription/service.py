from __future__ import annotations

import random
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from types import MappingProxyType

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.redis import RedisCache
from app.providers.base.models import ProviderKind
from app.subscription.generator import SubscriptionGenerator
from app.subscription.models import ProviderConfig, RenderedFeed
from app.subscription.renderer import SubscriptionRenderer
from app.subscription.repository import SubscriptionRepository, UserTrafficStats
from app.subscription.schemas import (
    ConfigRead,
    FeedRead,
    FeedRequest,
    FeedScope,
    RenderVersion,
    SubscriptionFormat,
)

_PLACEHOLDER_UUID = "00000000-0000-0000-0000-000000000000"

logger = get_logger("xlink.subscription")


class SubscriptionService:
    def __init__(
        self,
        repository: SubscriptionRepository,
        generator: SubscriptionGenerator,
        renderer: SubscriptionRenderer,
        cache: RedisCache,
    ) -> None:
        self._repository = repository
        self._generator = generator
        self._renderer = renderer
        self._cache = cache

    async def generate_config(self, assignment_id: uuid.UUID) -> ConfigRead:
        source = await self._repository.get_assignment_source(assignment_id)
        if source is None:
            raise NotFoundError("Assignment not found.", code="assignment_not_found")
        config = await self._generator.generate_config(source)
        rendered = self._renderer.render_config(config)
        return self._config_read(config, rendered.uri)

    async def assignment_feed(
        self, assignment_id: uuid.UUID, *, use_cache: bool = True
    ) -> FeedRead:
        return await self.feed(
            FeedRequest(scope=FeedScope.ASSIGNMENT, subject_id=assignment_id, use_cache=use_cache)
        )

    async def profile_feed(self, profile_id: uuid.UUID, *, use_cache: bool = True) -> FeedRead:
        return await self.feed(
            FeedRequest(scope=FeedScope.PROFILE, subject_id=profile_id, use_cache=use_cache)
        )

    async def user_feed(self, user_id: uuid.UUID, *, use_cache: bool = True) -> FeedRead:
        return await self.feed(
            FeedRequest(scope=FeedScope.USER, subject_id=user_id, use_cache=use_cache)
        )

    async def feed(self, request: FeedRequest) -> FeedRead:
        if request.scope is FeedScope.USER:
            await self._repository.activate_on_hold(request.subject_id)
            await self._enforce_user_quota(request.subject_id)

        use_cache = request.use_cache and not request.shuffle
        cache_key = self._cache_key(request)
        if use_cache:
            cached = await self._read_cache(cache_key)
            if cached is not None:
                return cached

        configs = await self._generate_feed_configs(request)
        if request.shuffle:
            configs = tuple(random.sample(configs, len(configs)))
        rendered = self._renderer.render_feed(
            configs,
            version=request.version,
            feed_format=request.format,
        )
        response = self._feed_read(rendered)
        if use_cache:
            await self._cache.set_json(cache_key, response.model_dump(mode="json"))
        return response

    async def placeholder_feed(
        self,
        remark: str,
        feed_format: SubscriptionFormat,
        version: RenderVersion = RenderVersion.V1,
    ) -> FeedRead:
        config = ProviderConfig(
            assignment_id=uuid.UUID(_PLACEHOLDER_UUID),
            user_id=uuid.UUID(_PLACEHOLDER_UUID),
            provider_kind=ProviderKind.XRAY,
            provider_name="placeholder",
            protocol="vless",
            client_id=_PLACEHOLDER_UUID,
            email=None,
            inbound_tag="placeholder",
            host="127.0.0.1",
            port=1,
            expires_at=None,
            traffic_limit_bytes=None,
            settings=MappingProxyType(
                {
                    "uuid": _PLACEHOLDER_UUID,
                    "remark": remark,
                    "network": "tcp",
                    "security": "none",
                }
            ),
        )
        rendered = self._renderer.render_feed((config,), version=version, feed_format=feed_format)
        return self._feed_read(rendered)

    async def _enforce_user_quota(self, user_id: uuid.UUID) -> None:
        stats = await self._repository.get_user_quota(user_id)
        now_ts = int(datetime.now(UTC).timestamp())
        if stats.expire_timestamp is not None and stats.expire_timestamp < now_ts:
            raise ValidationError("Subscription has expired.", code="subscription_expired")
        if stats.traffic_limit_bytes is not None and stats.used_bytes >= stats.traffic_limit_bytes:
            raise ValidationError("Data limit reached.", code="subscription_limit_reached")

    async def _generate_feed_configs(self, request: FeedRequest) -> tuple[ProviderConfig, ...]:
        if request.scope is FeedScope.ASSIGNMENT:
            sources = await self._repository.list_assignment_sources(request.subject_id)
        elif request.scope is FeedScope.PROFILE:
            sources = await self._repository.list_profile_sources(request.subject_id)
        else:
            sources = await self._repository.list_user_sources(request.subject_id)
            pinned = await self._repository.pinned_node_ids(request.subject_id)
            if pinned:
                pinned_set = {str(n) for n in pinned}
                sources = [s for s in sources if str(s.node.id) in pinned_set]
        texts = await self._repository.get_status_texts()
        profile_ids = list({s.profile.id for s in sources})
        overrides = await self._repository.host_overrides(profile_ids)
        return await self._generator.generate_feed(sources, texts, overrides)

    def _feed_read(self, rendered: RenderedFeed) -> FeedRead:
        return FeedRead(
            content=rendered.content,
            version=rendered.version,
            content_hash=rendered.content_hash,
            etag=rendered.etag,
            expires_at=rendered.expires_at,
            items=tuple(self._config_read(item.config, item.uri) for item in rendered.configs),
        )

    def _config_read(self, config: ProviderConfig, uri: str) -> ConfigRead:
        return ConfigRead(
            assignment_id=config.assignment_id,
            provider=config.provider_name,
            protocol=config.protocol,
            uri=uri,
            expires_at=config.expires_at,
        )

    async def _read_cache(self, cache_key: str) -> FeedRead | None:
        try:
            cached = await self._cache.get_json(cache_key)
        except Exception:
            logger.warning("subscription_cache_read_failed", cache_key=cache_key)
            return None
        if cached is None:
            return None
        try:
            return FeedRead.model_validate(cached)
        except Exception:
            logger.warning("subscription_cache_corrupt", cache_key=cache_key)
            await self._cache.delete(cache_key)
            return None

    async def get_user_traffic_stats(self, user_id: uuid.UUID) -> UserTrafficStats:
        return await self._repository.get_user_traffic_stats(user_id)

    async def get_user_quota(self, user_id: uuid.UUID) -> UserTrafficStats:
        return await self._repository.get_user_quota(user_id)

    async def invalidate_cache(self, pattern: str = "subscription:*") -> None:
        # Chunked scan+delete — never materialize the whole keyspace into one list
        # + one giant DEL (memory spike + Redis block on a hot mutation path).
        deleted = await self._cache.delete_by_pattern(pattern)
        logger.info("subscription_cache_invalidated", pattern=pattern, deleted=deleted)

    async def invalidate_subjects(self, subject_ids: Sequence[uuid.UUID]) -> None:
        deleted = 0
        for sid in subject_ids:
            deleted += await self._cache.delete_by_pattern(f"subscription:{sid}:*")
        if deleted:
            logger.info("subscription_cache_invalidated_subjects", subjects=len(subject_ids), deleted=deleted)

    async def notify_node_changed(self, node_id: uuid.UUID) -> None:
        await self._cache.publish_node_event(node_id, "config_changed")

    def _cache_key(self, request: FeedRequest) -> str:
        return (
            "subscription:"
            f"{request.subject_id}:"
            f"{request.scope.value}:"
            f"{request.version.value}:"
            f"{request.format.value}"
        )
