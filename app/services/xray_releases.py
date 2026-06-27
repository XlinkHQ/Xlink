from __future__ import annotations

import json
import urllib.error
import urllib.request

import anyio

from app.core.logging import get_logger
from app.db.redis import RedisCache

logger = get_logger("xlink.xray_releases")

_CACHE_KEY = "xray:releases"
_CACHE_TTL = 3600
_RELEASES_URL = "https://api.github.com/repos/XTLS/Xray-core/releases?per_page=40"
_MAX_VERSIONS = 12
_FALLBACK = ["v25.3.6", "v24.12.31", "v24.11.30", "v1.8.24", "v1.8.23"]


class XrayReleaseService:
    def __init__(self, cache: RedisCache) -> None:
        self._cache = cache

    async def versions(self) -> list[str]:
        cached = await self._cache.get_json(_CACHE_KEY)
        if isinstance(cached, list) and cached:
            return cached
        fetched = await anyio.to_thread.run_sync(self._fetch)
        versions = fetched or _FALLBACK
        await self._cache.set_json(_CACHE_KEY, versions, ttl=_CACHE_TTL)
        return versions

    def _fetch(self) -> list[str]:
        request = urllib.request.Request(
            _RELEASES_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "xlink"},
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                data = json.loads(response.read() or b"[]")
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            logger.warning("xray_releases_fetch_failed", error=str(exc))
            return []
        stable: list[str] = []
        seen: set[str] = set()
        for r in data:
            if not isinstance(r, dict):
                continue
            tag = r.get("tag_name")
            if not tag or r.get("draft") or r.get("prerelease"):
                continue
            tag = str(tag)
            if tag in seen:
                continue
            seen.add(tag)
            stable.append(tag)
        return stable[:_MAX_VERSIONS]
