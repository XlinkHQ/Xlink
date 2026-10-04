"""Pins the durable queue's guarantees: ack on success, retry with backoff,
dead-letter after max attempts, and — the reason it exists — no loss when a
worker dies mid-job."""

from __future__ import annotations

import time

import fakeredis
import fakeredis.aioredis
import pytest

from app.core.queue import DEAD, DELAYED, STREAM, DurableQueue


@pytest.fixture
async def r():
    # A fresh FakeServer per test: FakeRedis instances otherwise share one
    # default server, so a delayed retry parked by one test leaks into the next.
    client = fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=False)
    yield client
    await client.aclose()


def _q(r, **kw) -> DurableQueue:
    kw.setdefault("base_backoff", 0.0)  # retries due immediately in tests
    return DurableQueue(r, **kw)


async def test_success_is_acked_and_removed(r) -> None:
    q = _q(r)
    seen = []

    async def h(p):
        seen.append(p)

    q.register("k", h)
    await q.enqueue("k", {"n": 1})
    await q.run_once(block_ms=10)

    assert seen == [{"n": 1}]
    assert (await q.stats()) == {"queued": 0, "in_flight": 0, "delayed": 0, "dead": 0}


async def test_failure_is_retried_then_succeeds(r) -> None:
    q = _q(r, max_attempts=5)
    calls = 0

    async def flaky(_p):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("upstream 503")

    q.register("k", flaky)
    await q.enqueue("k", {})
    for _ in range(5):
        await q.run_once(block_ms=10)

    assert calls == 3
    assert (await q.stats())["dead"] == 0


async def test_backoff_delays_the_retry(r) -> None:
    q = _q(r, base_backoff=60.0)

    async def boom(_p):
        raise RuntimeError("nope")

    q.register("k", boom)
    await q.enqueue("k", {})
    await q.run_once(block_ms=10)

    stats = await q.stats()
    assert stats["delayed"] == 1, "failed job should be parked, not re-run immediately"
    assert stats["queued"] == 0
    (_, score), = await r.zrange(DELAYED, 0, -1, withscores=True)
    assert score > time.time() + 50


async def test_dead_letters_after_max_attempts(r) -> None:
    q = _q(r, max_attempts=3)

    async def always_fails(_p):
        raise ValueError("bad payload")

    q.register("k", always_fails)
    await q.enqueue("k", {"id": 7})
    for _ in range(6):
        await q.run_once(block_ms=10)

    dead = await q.dead_letters()
    assert len(dead) == 1
    assert dead[0]["kind"] == "k"
    assert "bad payload" in dead[0]["reason"]
    assert (await q.stats())["queued"] == 0


async def test_unknown_kind_is_dead_lettered_not_lost(r) -> None:
    q = _q(r)
    await q.enqueue("nobody-handles-this", {})
    await q.run_once(block_ms=10)
    assert (await q.dead_letters())[0]["reason"].startswith("no handler")


async def test_job_survives_a_worker_crash(r) -> None:
    """The headline guarantee. Worker A reads a job and dies before acking;
    worker B must pick it up rather than the job being lost."""
    a = _q(r, consumer="worker-a", visibility_timeout_ms=0)
    await a.enqueue("k", {"important": True})
    await a._ensure_group()
    # A reads it (now pending against A) and then "crashes" — no ack.
    await r.xreadgroup("xlink-workers", "worker-a", {STREAM: ">"}, count=1)

    b = _q(r, consumer="worker-b", visibility_timeout_ms=0)
    got = []

    async def h(p):
        got.append(p)

    b.register("k", h)
    await b.run_once(block_ms=10)

    assert got == [{"important": True}]
    assert (await b.stats())["in_flight"] == 0


async def test_poison_pill_is_dead_lettered_instead_of_looping(r) -> None:
    """A job that kills its worker every time must not crash-loop forever."""
    q = _q(r, consumer="w", visibility_timeout_ms=0, max_attempts=2)
    await q.enqueue("k", {})
    await q._ensure_group()
    for _ in range(4):
        # read-and-crash, repeatedly
        await r.xreadgroup("xlink-workers", "w", {STREAM: ">"}, count=1)
        await q._reclaim_stale()
    assert (await q.stats())["dead"] == 1


async def test_dead_letter_can_be_retried(r) -> None:
    q = _q(r, max_attempts=1)
    ok = False

    async def h(_p):
        if not ok:
            raise RuntimeError("down")

    q.register("k", h)
    await q.enqueue("k", {"x": 1})
    await q.run_once(block_ms=10)
    (dead,) = await q.dead_letters()

    ok = True
    assert await q.retry_dead(dead["id"]) is True
    await q.run_once(block_ms=10)
    assert (await q.stats()) == {"queued": 0, "in_flight": 0, "delayed": 0, "dead": 0}


async def test_two_promoters_do_not_duplicate_a_retry(r) -> None:
    q1, q2 = _q(r, consumer="a"), _q(r, consumer="b")
    await q1._ensure_group()
    member = '{"kind": "k", "payload": "{}", "attempt": "1", "max_attempts": "5"}'
    await r.zadd(DELAYED, {member: 0})
    moved = await q1._promote_delayed() + await q2._promote_delayed()
    assert moved == 1
    assert await r.xlen(STREAM) == 1


async def test_payload_never_needs_secrets(r) -> None:
    """Sanity on the dead-letter view: it exposes kind/reason, not the payload."""
    q = _q(r, max_attempts=1)
    q.register("k", lambda _p: (_ for _ in ()).throw(RuntimeError("x")))  # type: ignore[arg-type]
    await q.enqueue("k", {"token": "SECRET"})
    await q.run_once(block_ms=10)
    view = (await q.dead_letters())[0]
    assert "SECRET" not in str(view)
    assert await r.xlen(DEAD) == 1


async def test_rapid_retries_are_never_skipped(r) -> None:
    """Regression: acked entries used to be XDEL-ed. Re-adding in the same
    millisecond could then mint an id at or below the group cursor, and
    XREADGROUP '>' skipped the retry forever — losing exactly the work this
    queue exists to keep. Hammer it: every job must reach the dead stream."""
    q = _q(r, max_attempts=3)

    async def boom(_p):
        raise RuntimeError("down")

    q.register("k", boom)
    for i in range(25):
        await q.enqueue("k", {"i": i})
    for _ in range(40):
        await q.run_once(block_ms=1)

    assert (await q.stats())["dead"] == 25


async def test_trim_never_drops_undelivered_work(r) -> None:
    q = _q(r)
    seen = []

    async def h(p):
        seen.append(p["i"])

    q.register("k", h)
    await q.enqueue("k", {"i": 0})
    await q.run_once(block_ms=1)  # delivers + acks #0, then trims
    for i in range(1, 6):
        await q.enqueue("k", {"i": i})  # backlog not yet read

    await q._trim()
    assert (await q.stats())["queued"] == 5, "trim removed undelivered backlog"

    await q.run_once(block_ms=1)
    assert sorted(seen) == [0, 1, 2, 3, 4, 5]


async def test_idle_loop_does_not_starve_the_event_loop(r) -> None:
    """Regression: with a server that returns from XREADGROUP BLOCK immediately
    (fakeredis does), the consumer loop never suspended and pinned a core while
    starving every other task. An idle loop must hand control back."""
    import asyncio

    q = _q(r)
    ticks = 0

    async def other():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0)

    o = asyncio.create_task(other())
    q.start()
    await asyncio.sleep(0.6)
    await q.stop()
    o.cancel()
    assert ticks > 10, f"queue loop starved the event loop ({ticks} turns)"
