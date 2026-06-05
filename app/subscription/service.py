from __future__ import annotations

import uuid

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.redis import RedisCache
from app.subscription.generator import SubscriptionGenerator
from app.subscription.models import ProviderConfig, RenderedFeed
from app.subscription.renderer import SubscriptionRenderer
from app.subscription.repository import SubscriptionRepository
from app.subscription.schemas import ConfigRead, FeedRead, FeedRequest, FeedScope

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
        cache_key = self._cache_key(request)
        if request.use_cache:
            cached = await self._read_cache(cache_key)
            if cached is not None:
                return cached

        configs = await self._generate_feed_configs(request)
        rendered = self._renderer.render_feed(
            configs,
            version=request.version,
            feed_format=request.format,
        )
        response = self._feed_read(rendered)
        if request.use_cache:
            await self._cache.set_json(cache_key, response.model_dump(mode="json"))
        return response

    async def _generate_feed_configs(self, request: FeedRequest) -> tuple[ProviderConfig, ...]:
        if request.scope is FeedScope.ASSIGNMENT:
            sources = await self._repository.list_assignment_sources(request.subject_id)
        elif request.scope is FeedScope.PROFILE:
            sources = await self._repository.list_profile_sources(request.subject_id)
        else:
            sources = await self._repository.list_user_sources(request.subject_id)
        return await self._generator.generate_feed(sources)

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

    def _cache_key(self, request: FeedRequest) -> str:
        return (
            "subscription:"
            f"{request.version.value}:"
            f"{request.format.value}:"
            f"{request.scope.value}:"
            f"{request.subject_id}"
        )
