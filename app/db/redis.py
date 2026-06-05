from __future__ import annotations

from typing import Any

import orjson
from redis.asyncio import ConnectionPool, Redis

from app.core.config import Settings


class RedisCache:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool = ConnectionPool.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            decode_responses=False,
        )
        self._client: Redis = Redis(connection_pool=self._pool)

    @property
    def client(self) -> Redis:
        return self._client

    async def get_json(self, key: str) -> Any | None:
        raw = await self._client.get(key)
        return orjson.loads(raw) if raw is not None else None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        await self._client.set(
            key,
            orjson.dumps(value),
            ex=ttl if ttl is not None else self._settings.cache_ttl_seconds,
        )

    async def delete(self, *keys: str) -> None:
        if keys:
            await self._client.delete(*keys)

    async def ping(self) -> bool:
        return bool(await self._client.ping())

    async def close(self) -> None:
        await self._client.aclose()
        await self._pool.disconnect()
