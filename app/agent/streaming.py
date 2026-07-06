from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

import orjson

from app.db.redis import RedisCache

_METRICS_PREFIX = "xlink:agent:metrics:"
_LOGS_PREFIX = "xlink:agent:logs:"
_MAX_METRICS = 1000
_MAX_LOGS = 1000
_TTL_SECONDS = 3600


class AgentStreamService:
    def __init__(
        self,
        cache: RedisCache,
        *,
        max_metrics: int = _MAX_METRICS,
        max_logs: int = _MAX_LOGS,
        ttl_seconds: int = _TTL_SECONDS,
    ) -> None:
        self._cache = cache
        self._max_metrics = max_metrics
        self._max_logs = max_logs
        self._ttl = ttl_seconds

    async def push_metrics(self, node_id: uuid.UUID, samples: Sequence[dict]) -> tuple[int, int]:
        return await self._push(_METRICS_PREFIX + str(node_id), samples, self._max_metrics)

    async def push_logs(self, node_id: uuid.UUID, lines: Sequence[dict]) -> tuple[int, int]:
        return await self._push(_LOGS_PREFIX + str(node_id), lines, self._max_logs)

    async def read_metrics(self, node_id: uuid.UUID, *, limit: int = 100) -> list[Any]:
        return await self._read(_METRICS_PREFIX + str(node_id), limit)

    async def read_logs(self, node_id: uuid.UUID, *, limit: int = 100) -> list[Any]:
        return await self._read(_LOGS_PREFIX + str(node_id), limit)

    async def _push(self, key: str, items: Sequence[dict], cap: int) -> tuple[int, int]:
        if not items:
            return 0, 0
        client = self._cache.client
        before = await client.llen(key)
        encoded = [orjson.dumps(item) for item in items]
        async with client.pipeline(transaction=True) as pipe:
            pipe.lpush(key, *encoded)
            pipe.ltrim(key, 0, cap - 1)
            pipe.expire(key, self._ttl)
            await pipe.execute()
        accepted = len(encoded)
        dropped = max(0, before + accepted - cap)
        return accepted, dropped

    async def _read(self, key: str, limit: int) -> list[Any]:
        raw = await self._cache.client.lrange(key, 0, max(1, limit) - 1)
        return [orjson.loads(item) for item in raw]
