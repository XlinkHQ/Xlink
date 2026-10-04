from __future__ import annotations

import asyncio
import random
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from types import MappingProxyType

from app.core.cache import CacheProtocol
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.providers.base.models import ProviderKind
from app.subscription import templates as client_templates
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

_GLOBAL_REV_KEY = "subscription:rev:__global__"


def _subject_rev_key(subject_id: uuid.UUID) -> str:
    return f"subscription:rev:{subject_id}"


logger = get_logger("xlink.subscription")


def _apply_asn_addresses(
    overrides: dict[uuid.UUID, list[dict]], asn: int | None
) -> dict[uuid.UUID, list[dict]]:
    """Swap each host's address for one of its clean addresses for this ASN,
    and drop the map itself so it never reaches a renderer."""
    out: dict[uuid.UUID, list[dict]] = {}
    for pid, hosts in overrides.items():
        fixed = []
        for h in hosts:
            mapping = h.get("asn_addresses")
            if mapping is None:
                fixed.append(h)
                continue
            h = {k: v for k, v in h.items() if k != "asn_addresses"}
            choices = mapping.get(str(asn)) if asn else None
            if choices:
                h["address"] = random.choice(choices)
            fixed.append(h)
        out[pid] = fixed
    return out


class SubscriptionService:
    def __init__(
        self,
        repository: SubscriptionRepository,
        generator: SubscriptionGenerator,
        renderer: SubscriptionRenderer,
        cache: CacheProtocol,
    ) -> None:
        self._repository = repository
        self._generator = generator
        self._renderer = renderer
        self._cache = cache
        self._inflight: dict[str, asyncio.Lock] = {}
        self._asn_cache: tuple[float, frozenset[int]] | None = None

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
            if request.activate_first_use:
                await self._repository.activate_on_hold(request.subject_id)
            await self._enforce_user_quota(request.subject_id)

        use_cache = request.use_cache and not request.shuffle
        if not use_cache:
            return await self._render_feed(request)

        cache_key = await self._cache_key(request)
        if cache_key is None:
            # Revisions unreadable: serving from (or writing to) a guessed key
            # would resurrect pre-invalidation configs. Render fresh instead.
            return await self._render_feed(request)

        cached = await self._read_cache(cache_key)
        if cached is not None:
            return cached

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
        with client_templates.use(await self._load_templates()):
            rendered = self._renderer.render_feed(
                configs,
                version=request.version,
                feed_format=request.format,
            )
        return self._feed_read(rendered)

    async def _load_templates(self) -> dict[str, dict]:
        loader = getattr(self._repository, "default_client_templates", None)
        if loader is None:
            return {}
        parsed: dict[str, dict] = {}
        for fmt, content in (await loader()).items():
            try:
                parsed[fmt] = client_templates.parse(fmt, content)
            except ValidationError:
                # Validated on save; a row that no longer parses (manual DB
                # edit) must not take every subscription down with it.
                logger.warning("client_template_unparseable", format=fmt)
        return parsed

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
        if overrides:
            overrides = _apply_asn_addresses(overrides, request.client_asn)
        return await self._generator.generate_feed(sources, texts, overrides)

    async def mapped_asns(self) -> frozenset[int]:
        """ASNs any host maps to clean addresses (cached briefly in-process;
        host edits invalidate feeds, and a 30 s lag here only delays which
        cache bucket a new mapping uses)."""
        now = time.monotonic()
        cached = self._asn_cache
        if cached is not None and now - cached[0] < 30:
            return cached[1]
        loader = getattr(self._repository, "mapped_asns", None)
        asns = frozenset(await loader()) if loader else frozenset()
        self._asn_cache = (now, asns)
        return asns

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
        rev = await self._cache.incr(_GLOBAL_REV_KEY)
        # Durable witness, so an evicted counter is not mistaken for "never
        # invalidated" — see _cache_key.
        await self._cache.mark_invalidated(_GLOBAL_REV_KEY)
        logger.info("subscription_cache_invalidated", global_rev=rev)

    async def invalidate_subjects(self, subject_ids: Sequence[uuid.UUID]) -> None:
        for sid in subject_ids:
            await self._cache.incr(_subject_rev_key(sid))
            await self._cache.mark_invalidated(sid)
        if subject_ids:
            logger.info("subscription_cache_invalidated_subjects", subjects=len(subject_ids))

    async def invalidate_subject(self, subject_id: uuid.UUID) -> None:
        await self._cache.incr(_subject_rev_key(subject_id))
        await self._cache.mark_invalidated(subject_id)

    async def notify_node_changed(self, node_id: uuid.UUID) -> None:
        await self._cache.publish_node_event(node_id, "config_changed")

    async def _cache_key(self, request: FeedRequest) -> str | None:
        """Versioned cache key, or None when the revisions cannot be trusted.

        Invalidation is revision-based: revoking a subscription bumps a counter
        and the old key is orphaned. Falling back to a fixed ``g0:r0`` on a read
        failure pointed straight back at the generation that existed before any
        invalidation ever happened — and the write path then refreshed that slot,
        so the stale entry never even aged out.

        This is reachable without an outage: the revision counters are written
        with INCR and carry no TTL, while Redis runs ``allkeys-lru``, so an
        eviction alone was enough to resurrect revoked configs. When the
        revisions are unavailable we now skip the cache entirely and serve a
        freshly rendered feed.
        """
        try:
            global_rev, subject_rev = await self._cache.mget_int(
                [_GLOBAL_REV_KEY, _subject_rev_key(request.subject_id)]
            )
        except Exception:
            logger.warning("subscription_cache_key_redis_error")
            return None
        # An absent counter is ambiguous: "never invalidated" (generation zero
        # is genuinely correct) looks exactly like "evicted" (generation zero is
        # the pre-revocation key, and serving it resurrects revoked configs).
        # The ambiguity is resolved at WRITE time — every invalidation leaves a
        # durable marker — so absent counter + marker present means evicted.
        try:
            if global_rev is None and await self._cache.invalidation_seen(_GLOBAL_REV_KEY):
                logger.warning("subscription_cache_revision_evicted", scope="global")
                return None
            if subject_rev is None and await self._cache.invalidation_seen(
                request.subject_id
            ):
                logger.warning(
                    "subscription_cache_revision_evicted",
                    subject_id=str(request.subject_id),
                )
                return None
        except Exception:
            logger.warning("subscription_cache_revision_check_failed")
            return None
        return (
            "subscription:"
            f"{request.subject_id}:"
            f"{request.scope.value}:"
            f"{request.version.value}:"
            f"{request.format.value}:"
            f"g{global_rev or 0}:"
            f"r{subject_rev or 0}"
            + (f":a{request.client_asn}" if request.client_asn else "")
        )
