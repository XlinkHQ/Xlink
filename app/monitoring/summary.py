from __future__ import annotations

import asyncio
import contextlib

from app.core.cache import CacheProtocol
from app.core.logging import get_logger
from app.db.session import Database
from app.monitoring.metrics import MetricsCollector, snapshot_from_summary
from app.monitoring.models import MetricsSnapshot
from app.providers.base.registry import ProviderRegistry

logger = get_logger("xlink.monitoring.summary")

_SUMMARY_KEY = "xlink:metrics:summary"


class MetricsSummaryCache:
    def __init__(
        self,
        cache: CacheProtocol,
        providers: ProviderRegistry,
        *,
        ttl_seconds: int = 60,
    ) -> None:
        self._cache = cache
        self._providers = providers
        self._ttl = ttl_seconds

    async def read(self) -> dict[str, float] | None:
        try:
            data = await self._cache.get_json(_SUMMARY_KEY)
        except Exception:
            logger.warning("metrics_summary_cache_read_failed")
            return None
        if not isinstance(data, dict):
            return None
        try:
            return {str(k): float(v) for k, v in data.items()}
        except (ValueError, TypeError):
            logger.warning("metrics_summary_cache_data_invalid")
            return None

    async def write(self, summary: dict[str, float]) -> None:
        try:
            await self._cache.set_json(_SUMMARY_KEY, summary, ttl=self._ttl)
        except Exception:
            logger.warning("metrics_summary_cache_write_failed")

    async def snapshot(self, summary: dict[str, float]) -> MetricsSnapshot:
        return await snapshot_from_summary(summary, self._providers)


async def refresh_summary(
    db: Database,
    cache: CacheProtocol,
    providers: ProviderRegistry,
    *,
    ttl_seconds: int = 60,
) -> dict[str, float]:
    async with db.session() as session:
        collector = MetricsCollector(session, providers)
        summary = await collector.collect_summary()
    await MetricsSummaryCache(cache, providers, ttl_seconds=ttl_seconds).write(summary)
    return summary


class MetricsRefreshJob:
    def __init__(
        self,
        db: Database,
        cache: CacheProtocol,
        providers: ProviderRegistry,
        *,
        interval_seconds: int,
        ttl_seconds: int,
        leader=None,
    ) -> None:
        self._db = db
        self._cache = cache
        self._providers = providers
        self._interval = interval_seconds
        self._ttl = ttl_seconds
        self._leader = leader
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="metrics-refresh")
        logger.info("metrics_refresh_started", interval_seconds=self._interval)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
        logger.info("metrics_refresh_stopped")

    def _is_leader(self) -> bool:
        return self._leader is None or self._leader.is_leader

    async def _run(self) -> None:
        if self._is_leader():
            try:
                await refresh_summary(self._db, self._cache, self._providers, ttl_seconds=self._ttl)
            except Exception:
                logger.exception("metrics_refresh_failed")
        while not self._stopping.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            if self._stopping.is_set():
                break
            # Only the leader refreshes — otherwise N replicas each run the full
            # collect + last-writer-wins on one Redis key.
            if not self._is_leader():
                continue
            try:
                await refresh_summary(self._db, self._cache, self._providers, ttl_seconds=self._ttl)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("metrics_refresh_failed")
