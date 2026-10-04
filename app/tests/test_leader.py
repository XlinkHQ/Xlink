"""Leader election is what stops every replica from running the background jobs
at once. A silent failure here double-counts traffic rollups and reruns
cleanups, so the contract is pinned down explicitly."""

from __future__ import annotations

import asyncio
from typing import Any

import fakeredis.aioredis
import pytest

from app.core.jobs import TokenCleanupJob
from app.core.leader import LeaderElector


class _Cache:
    """Minimal CacheProtocol stand-in: the elector only touches `.client`."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @property
    def client(self) -> Any:
        return self._client


@pytest.fixture
def redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=False)


async def test_acquires_leadership_when_key_is_free(redis) -> None:
    elector = LeaderElector(_Cache(redis), ttl_seconds=30)
    assert elector.is_leader is False
    assert await elector._try_acquire_or_renew() is True


async def test_second_elector_does_not_acquire_while_first_holds(redis) -> None:
    first = LeaderElector(_Cache(redis), ttl_seconds=30)
    second = LeaderElector(_Cache(redis), ttl_seconds=30)
    second._id = "other-host:999"

    assert await first._try_acquire_or_renew() is True
    first._is_leader = True

    # The key is held by `first`, so `second` must not win it.
    assert await second._try_acquire_or_renew() is False
    assert second.is_leader is False


async def test_leader_renews_its_own_key(redis) -> None:
    elector = LeaderElector(_Cache(redis), ttl_seconds=30)
    assert await elector._try_acquire_or_renew() is True
    elector._is_leader = True

    # Renewal path: the key still carries our id, so the Lua CAS succeeds.
    assert await elector._try_acquire_or_renew() is True
    assert elector.is_leader is True


async def test_leader_stands_down_when_its_key_was_taken(redis) -> None:
    elector = LeaderElector(_Cache(redis), ttl_seconds=30)
    await elector._try_acquire_or_renew()
    elector._is_leader = True

    # Someone else's id is now under the key — renewal must fail and we drop out.
    await redis.set("xlink:leader", b"someone-else:1")

    assert await elector._try_acquire_or_renew() is False
    assert elector.is_leader is False


async def test_leader_stands_down_when_key_expired(redis) -> None:
    elector = LeaderElector(_Cache(redis), ttl_seconds=30)
    await elector._try_acquire_or_renew()
    elector._is_leader = True

    await redis.delete("xlink:leader")

    assert await elector._try_acquire_or_renew() is False
    assert elector.is_leader is False


async def test_stop_releases_the_key_for_another_replica(redis) -> None:
    elector = LeaderElector(_Cache(redis), ttl_seconds=30)
    await elector._try_acquire_or_renew()
    elector._is_leader = True

    await elector.stop()

    assert elector.is_leader is False
    assert await redis.get("xlink:leader") is None

    # A fresh replica can now take over.
    successor = LeaderElector(_Cache(redis), ttl_seconds=30)
    successor._id = "successor:2"
    assert await successor._try_acquire_or_renew() is True


async def test_stop_does_not_release_a_key_owned_by_someone_else(redis) -> None:
    elector = LeaderElector(_Cache(redis), ttl_seconds=30)
    elector._is_leader = True
    await redis.set("xlink:leader", b"someone-else:1")

    await elector.stop()

    # The release is a CAS on our own id, so the real leader keeps its key.
    assert await redis.get("xlink:leader") == b"someone-else:1"


async def test_run_loop_sets_and_clears_is_leader(redis) -> None:
    elector = LeaderElector(_Cache(redis), ttl_seconds=3)
    elector.start()
    try:
        for _ in range(50):
            if elector.is_leader:
                break
            await asyncio.sleep(0.01)
        assert elector.is_leader is True
    finally:
        await elector.stop()
    assert elector.is_leader is False


async def test_election_error_does_not_leave_a_stale_leader(redis) -> None:
    class _Exploding:
        @property
        def client(self) -> Any:
            raise RuntimeError("redis is down")

    elector = LeaderElector(_Exploding(), ttl_seconds=3)
    elector._is_leader = True
    elector.start()
    try:
        for _ in range(50):
            if not elector.is_leader:
                break
            await asyncio.sleep(0.01)
        # Losing Redis must drop leadership, not keep running jobs blindly.
        assert elector.is_leader is False
    finally:
        await elector.stop()


async def test_non_leader_job_skips_its_work(redis, monkeypatch) -> None:
    """The whole point of the elector: a replica that is not leader must not
    run the job body."""
    calls = 0

    async def _counting_purge(_db: Any) -> int:
        nonlocal calls
        calls += 1
        return 0

    monkeypatch.setattr("app.core.jobs.purge_expired_tokens", _counting_purge)

    follower = LeaderElector(_Cache(redis), ttl_seconds=30)
    follower._is_leader = False

    job = TokenCleanupJob(db=None, interval_seconds=0, leader=follower)  # type: ignore[arg-type]
    job.start()
    await asyncio.sleep(0.05)
    await job.stop()
    assert calls == 0

    leader = LeaderElector(_Cache(redis), ttl_seconds=30)
    leader._is_leader = True
    job2 = TokenCleanupJob(db=None, interval_seconds=0, leader=leader)  # type: ignore[arg-type]
    job2.start()
    await asyncio.sleep(0.05)
    await job2.stop()
    assert calls > 0
