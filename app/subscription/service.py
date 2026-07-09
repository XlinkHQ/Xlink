from __future__ import annotations

import asyncio
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

# Global cache epoch — bumped instead of SCAN+deleting the whole subscription:*
# keyspace on a broad invalidation. Every feed key embeds the current epoch, so a
# single INCR (O(1)) makes every existing key unreachable; the stale keys expire
# by TTL rather than being deleted in a herd-inducing SCAN.
_GLOBAL_REV_KEY = "subscription:rev:__global__"


def _subject_rev_key(subject_id: uuid.UUID) -> str:
    # Per-subject monotonic cache revision. Bumping it (INCR, O(1)) invalidates
    # only that subject's cached feeds without touching anyone else's.
    return f"subscription:rev:{subject_id}"


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
        # In-process single-flight guards, keyed by cache_key. A cold-cache burst
        # for the SAME feed (e.g. all of one user's clients reconnecting after an
        # invalidation) then computes the feed once and the rest await the result
        # instead of every request re-running the full render (a stampede).
        self._inflight: dict[str, asyncio.Lock] = {}

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
            # Consuming the on-hold "first use" starts the expiry clock, so only do
            # it for a genuine client fetch — never for an admin/panel preview,
            # which would burn the customer's window on a read.
            if request.activate_first_use:
                await self._repository.activate_on_hold(request.subject_id)
            await self._enforce_user_quota(request.subject_id)

        use_cache = request.use_cache and not request.shuffle
        if not use_cache:
            return await self._render_feed(request)

        cache_key = await self._cache_key(request)
        cached = await self._read_cache(cache_key)
        if cached is not None:
            return cached

        # Cold cache: serialize concurrent computations of the SAME key so a burst
        # recomputes once, not N times. The DB read + render is the expensive part;
        # the winner writes the cache and the rest re-read it.
        lock = self._inflight.setdefault(cache_key, asyncio.Lock())
        try:
            async with lock:
                cached = await self._read_cache(cache_key)
                if cached is not None:
                    return cached
                response = await self._render_feed(request)
                await self._cache.set_json(cache_key, response.model_dump(mode="json"))
                return response
        finally:
            # Evict the lock once we've released it AND no other coroutine is
            # queued on it — otherwise the map grows by one Lock per distinct
            # cache key (each epoch/revision bump mints new keys) and never
            # shrinks. Checked OUTSIDE the `async with` so the lock is already
            # released; `_waiters` being falsy means we were the last user.
            if (
                self._inflight.get(cache_key) is lock
                and not lock.locked()
                and not getattr(lock, "_waiters", None)
            ):
                self._inflight.pop(cache_key, None)

    async def _render_feed(self, request: FeedRequest) -> FeedRead:
        configs = await self._generate_feed_configs(request)
        if request.shuffle:
            configs = tuple(random.sample(configs, len(configs)))
        rendered = self._renderer.render_feed(
            configs,
            version=request.version,
            feed_format=request.format,
        )
        return self._feed_read(rendered)

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
        # Broad invalidation is now O(1): bump the global cache epoch so every
        # existing feed key (which embeds the epoch) becomes unreachable at once.
        # Stale keys expire by TTL instead of a SCAN+DEL over the whole keyspace,
        # which used to cold-wipe every user's cache and cause a recompute
        # stampede. `pattern` is accepted for backwards compatibility but ignored.
        rev = await self._cache.incr(_GLOBAL_REV_KEY)
        logger.info("subscription_cache_invalidated", global_rev=rev)

    async def invalidate_subjects(self, subject_ids: Sequence[uuid.UUID]) -> None:
        # Per-subject invalidation is O(1) per subject: bump each subject's cache
        # revision (INCR). No SCAN, no herd — only the affected subjects' keys go
        # stale, and they expire by TTL.
        for sid in subject_ids:
            await self._cache.incr(_subject_rev_key(sid))
        if subject_ids:
            logger.info("subscription_cache_invalidated_subjects", subjects=len(subject_ids))

    async def invalidate_subject(self, subject_id: uuid.UUID) -> None:
        await self._cache.incr(_subject_rev_key(subject_id))

    async def notify_node_changed(self, node_id: uuid.UUID) -> None:
        await self._cache.publish_node_event(node_id, "config_changed")

    async def _cache_key(self, request: FeedRequest) -> str:
        # Embed both the global epoch and the per-subject revision so invalidation
        # is a counter bump (O(1)) rather than a keyspace SCAN+delete. A read that
        # races an invalidation simply misses (new rev) and recomputes — never
        # serves stale.
        global_rev, subject_rev = await self._cache.mget_int(
            [_GLOBAL_REV_KEY, _subject_rev_key(request.subject_id)]
        )
        return (
            "subscription:"
            f"{request.subject_id}:"
            f"{request.scope.value}:"
            f"{request.version.value}:"
            f"{request.format.value}:"
            f"g{global_rev or 0}:"
            f"r{subject_rev or 0}"
        )
