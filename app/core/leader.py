from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import time
import uuid

from app.core.cache import CacheProtocol
from app.core.logging import get_logger

logger = get_logger("xlink.leader")

_LEADER_KEY = "xlink:leader"

_RENEW_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('pexpire', KEYS[1], ARGV[2])
else
  return 0
end
"""
_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""


class LeaderElector:
    """Redis-backed leader election so background jobs run on exactly one
    replica at a time. The leader holds a TTL'd key and renews it; if it dies,
    the key expires and another replica takes over within one TTL window.
    """

    def __init__(self, cache: CacheProtocol, *, ttl_seconds: int = 30) -> None:
        self._cache = cache
        self._ttl = ttl_seconds
        # hostname:pid alone collides across containers that share a hostname
        # and run as PID 1; two replicas with one id would both "renew".
        self._id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._is_leader = False
        # Monotonic deadline of the last confirmed hold. A process stalled past
        # its TTL (GC pause, SIGSTOP, a blocked loop) must stop acting as leader
        # by itself, before its next renew notices the key went to another
        # replica — otherwise both run jobs for up to one renew interval.
        self._valid_until = 0.0
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    @property
    def is_leader(self) -> bool:
        return self._is_leader and time.monotonic() < self._valid_until

    async def _try_acquire_or_renew(self) -> bool:
        client = self._cache.client
        # Stamp before the round-trip: the key's TTL started no later than
        # this, so the local deadline can only be conservative.
        started = time.monotonic()
        held = await self._acquire_or_renew(client)
        if held:
            self._valid_until = started + self._ttl * 2 / 3
        return held

    async def _acquire_or_renew(self, client) -> bool:  # noqa: ANN001
        if self._is_leader:
            renewed = await client.eval(_RENEW_LUA, 1, _LEADER_KEY, self._id, self._ttl * 1000)
            if int(renewed) == 1:
                return True
            self._is_leader = False
            return False
        acquired = await client.set(_LEADER_KEY, self._id, nx=True, ex=self._ttl)
        return bool(acquired)

    async def _run(self) -> None:
        interval = max(1, self._ttl // 3)
        while not self._stopping.is_set():
            try:
                leader = await self._try_acquire_or_renew()
                if leader and not self._is_leader:
                    self._is_leader = True
                    logger.info("leader_acquired", elector=self._id)
                elif not leader and self._is_leader:
                    self._is_leader = False
                    logger.info("leader_lost", elector=self._id)
                elif leader:
                    self._is_leader = True
            except Exception as exc:
                logger.warning("leader_election_error", error=str(exc))
                self._is_leader = False
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=interval)

    def start(self) -> None:
        if self._task is None:
            self._stopping.clear()
            self._task = asyncio.create_task(self._run(), name="leader-election")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._is_leader:
            # Best effort: with Redis gone the key simply expires on its own.
            with contextlib.suppress(Exception):
                await self._cache.client.eval(_RELEASE_LUA, 1, _LEADER_KEY, self._id)
        self._is_leader = False
