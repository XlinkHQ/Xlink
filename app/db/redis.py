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
        if raw is None:
            return None
        try:
            return orjson.loads(raw)
        except orjson.JSONDecodeError:
            await self._client.delete(key)
            return None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        await self._client.set(
            key,
            orjson.dumps(value),
            ex=ttl if ttl is not None else self._settings.cache_ttl_seconds,
        )

    async def delete(self, *keys: str) -> None:
        if keys:
            await self._client.delete(*keys)

    async def delete_by_pattern(self, pattern: str, *, chunk: int = 500) -> int:
        # Scan + delete in bounded chunks instead of materializing the whole
        # matched keyspace into one list and issuing one giant DEL — both grow
        # unbounded with user/feed count on wildcard patterns (subscription:*).
        deleted = 0
        buf: list[str] = []
        async for key in self._client.scan_iter(match=pattern, count=chunk):
            buf.append(key)
            if len(buf) >= chunk:
                deleted += await self._client.delete(*buf)
                buf.clear()
        if buf:
            deleted += await self._client.delete(*buf)
        return deleted

    @staticmethod
    def node_channel(node_id: object) -> str:
        return f"xlink:node-events:{node_id}"

    async def publish_node_event(self, node_id: object, event: str) -> None:
        await self._client.publish(self.node_channel(node_id), event)

    async def ping(self) -> bool:
        return bool(await self._client.ping())

    async def close(self) -> None:
        await self._client.aclose()
        await self._pool.disconnect()
