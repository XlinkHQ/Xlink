"""Revision-based invalidation must fail CLOSED.

`_cache_key` used to fall back to a fixed `g0:r0` whenever the revision
counters could not be read — which is exactly the key that existed before any
invalidation, so revoked configs came back. The write path then refreshed that
slot, so the staleness never even aged out via the TTL.

No outage is needed to trigger it: Redis runs `allkeys-lru` and the counters
are written with INCR, so they carry no TTL yet remain evictable.

An absent counter is ambiguous on its own — "never invalidated" (safe) looks
exactly like "evicted" (unsafe). The ambiguity is resolved at WRITE time: every
invalidation records a durable marker, so on read, absent counter + marker
present => evicted => refuse to serve a guessed key.
"""

from __future__ import annotations

import uuid

from app.subscription.schemas import (
    FeedRequest,
    FeedScope,
    RenderVersion,
    SubscriptionFormat,
)
from app.subscription.service import (
    _GLOBAL_REV_KEY,
    SubscriptionService,
    _subject_rev_key,
)


def _request(subject: uuid.UUID) -> FeedRequest:
    return FeedRequest(
        subject_id=subject,
        scope=FeedScope.USER,
        version=RenderVersion.V1,
        format=SubscriptionFormat.TEXT,
    )


def _service(cache) -> SubscriptionService:
    svc = SubscriptionService.__new__(SubscriptionService)
    svc._cache = cache
    return svc


async def test_fresh_subject_is_still_cacheable(app_state) -> None:
    """Nothing invalidated yet: generation zero is genuinely correct."""
    svc = _service(app_state.cache)
    key = await svc._cache_key(_request(uuid.uuid4()))
    assert key is not None
    assert key.endswith(":g0:r0")


async def test_key_changes_after_an_invalidation(app_state) -> None:
    subject = uuid.uuid4()
    svc = _service(app_state.cache)
    before = await svc._cache_key(_request(subject))

    await svc.invalidate_subject(subject)

    after = await svc._cache_key(_request(subject))
    assert after != before, "a revocation must orphan the old cache entry"


async def test_evicted_counter_refuses_to_serve_a_guessed_key(app_state) -> None:
    """The actual attack: LRU drops a bumped counter.

    Collapsing to g0:r0 here would hand back the pre-revocation generation.
    """
    subject = uuid.uuid4()
    svc = _service(app_state.cache)
    await svc.invalidate_subject(subject)
    assert await svc._cache_key(_request(subject)) is not None

    await app_state.cache.client.delete(_subject_rev_key(subject))

    assert await svc._cache_key(_request(subject)) is None


async def test_evicted_global_counter_also_refuses(app_state) -> None:
    subject = uuid.uuid4()
    svc = _service(app_state.cache)
    await svc.invalidate_cache()
    assert await svc._cache_key(_request(subject)) is not None

    await app_state.cache.client.delete(_GLOBAL_REV_KEY)

    assert await svc._cache_key(_request(subject)) is None


async def test_bulk_invalidation_marks_every_subject(app_state) -> None:
    subjects = [uuid.uuid4() for _ in range(3)]
    svc = _service(app_state.cache)
    await svc.invalidate_subjects(subjects)

    for sid in subjects:
        await app_state.cache.client.delete(_subject_rev_key(sid))
        assert await svc._cache_key(_request(sid)) is None, f"{sid} not protected"


async def test_redis_failure_bypasses_the_cache(app_state, monkeypatch) -> None:
    svc = _service(app_state.cache)

    async def _boom(_keys):
        raise RuntimeError("redis is down")

    monkeypatch.setattr(app_state.cache, "mget_int", _boom)
    assert await svc._cache_key(_request(uuid.uuid4())) is None


async def test_marker_survives_counter_loss(app_state) -> None:
    """The marker is the durable half; losing the counter must not lose it."""
    subject = uuid.uuid4()
    await app_state.cache.mark_invalidated(subject)
    await app_state.cache.client.delete(_subject_rev_key(subject))
    assert await app_state.cache.invalidation_seen(subject) is True
