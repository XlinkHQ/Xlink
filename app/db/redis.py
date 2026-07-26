from __future__ import annotations

import contextlib
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
            socket_timeout=settings.redis_socket_timeout,
            socket_connect_timeout=settings.redis_socket_connect_timeout,
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

    async def get_int(self, key: str) -> int | None:
        raw = await self._client.get(key)
        if raw is None:
            return None
        try:
            return int(raw)
        except (ValueError, TypeError):
            return None

    async def incr(self, key: str) -> int:
        return int(await self._client.incr(key))

    async def mget_int(self, keys: list[str]) -> list[int | None]:
        if not keys:
            return []
        raws = await self._client.mget(keys)
        out: list[int | None] = []
        for raw in raws:
            if raw is None:
                out.append(None)
                continue
            try:
                out.append(int(raw))
            except (ValueError, TypeError):
                out.append(None)
        return out

    @staticmethod
    def node_channel(node_id: object) -> str:
        return f"xlink:node-events:{node_id}"

    @staticmethod
    def node_config_key(node_id: object) -> str:
        return f"xlink:node-config:{node_id}"

    async def publish_node_event(self, node_id: object, event: str) -> None:
        if event == "config_changed":
            with contextlib.suppress(Exception):
                await self._client.delete(self.node_config_key(node_id))
        await self._client.publish(self.node_channel(node_id), event)

    async def get_node_config(self, node_id: object) -> Any | None:
        return await self.get_json(self.node_config_key(node_id))

    async def set_node_config(self, node_id: object, snapshot: Any, ttl: int) -> None:
        await self.set_json(self.node_config_key(node_id), snapshot, ttl=ttl)

    async def ping(self) -> bool:
        return bool(await self._client.ping())

    async def close(self) -> None:
        await self._client.aclose()
        await self._pool.disconnect()
