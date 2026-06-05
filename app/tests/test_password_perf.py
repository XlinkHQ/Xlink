from __future__ import annotations

import asyncio
import time
from itertools import pairwise

import anyio
from argon2 import PasswordHasher

from app.core import security
from app.core.security import (
    hash_password,
    hash_password_async,
    verify_password_async,
)

_SLOW_HASHER = PasswordHasher(time_cost=4, memory_cost=65536, parallelism=1)


async def _slow_hash_async(password: str) -> str:
    return await anyio.to_thread.run_sync(
        _SLOW_HASHER.hash, password, limiter=security._hash_limiter()
    )


async def _heartbeat(stop: asyncio.Event, ticks: list[float], interval: float) -> None:
    while not stop.is_set():
        ticks.append(time.perf_counter())
        await asyncio.sleep(interval)


async def test_hashing_does_not_block_event_loop() -> None:
    stop = asyncio.Event()
    ticks: list[float] = []
    interval = 0.005
    hb = asyncio.create_task(_heartbeat(stop, ticks, interval))

    work_start = time.perf_counter()
    await asyncio.gather(*(_slow_hash_async(f"loop-test-{i}") for i in range(8)))
    work_duration = time.perf_counter() - work_start

    stop.set()
    await hb

    gaps = [b - a for a, b in pairwise(ticks)]
    max_gap = max(gaps)
    assert work_duration > interval * 4, (
        "hashing finished too fast to be a meaningful non-blocking test"
    )
    assert max_gap < work_duration * 0.9, (
        f"event loop stalled for {max_gap:.3f}s during {work_duration:.3f}s of hashing"
    )


async def test_concurrent_hashing_runs_in_parallel() -> None:
    n = 4

    single_start = time.perf_counter()
    await _slow_hash_async("baseline-password")
    single = time.perf_counter() - single_start

    many_start = time.perf_counter()
    await asyncio.gather(*(_slow_hash_async(f"pw-{i}") for i in range(n)))
    many = time.perf_counter() - many_start

    assert many < single * n * 0.8, (
        f"{n} concurrent hashes took {many:.3f}s vs {single:.3f}s each — "
        "work does not appear to be offloaded in parallel"
    )


async def test_verify_async_matches_sync() -> None:
    digest = hash_password("verify-async-password")
    assert await verify_password_async("verify-async-password", digest) is True
    assert await verify_password_async("wrong-password", digest) is False


async def test_hash_async_roundtrip() -> None:
    digest = await hash_password_async("roundtrip-password")
    assert digest != "roundtrip-password"
    assert await verify_password_async("roundtrip-password", digest) is True
