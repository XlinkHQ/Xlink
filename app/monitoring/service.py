from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import RedisCache
from app.monitoring.exporters import PrometheusExporter
from app.monitoring.metrics import MetricsCollector
from app.monitoring.models import MetricsSnapshot
from app.monitoring.summary import MetricsSummaryCache
from app.providers.base.registry import ProviderRegistry


class MonitoringService:
    def __init__(
        self,
        session: AsyncSession,
        providers: ProviderRegistry,
        *,
        cache: RedisCache | None = None,
        summary_ttl_seconds: int = 60,
    ) -> None:
        self._collector = MetricsCollector(session, providers)
        self._providers = providers
        self._prometheus = PrometheusExporter()
        self._summary_cache = (
            MetricsSummaryCache(cache, providers, ttl_seconds=summary_ttl_seconds)
            if cache is not None
            else None
        )

    async def snapshot(self) -> MetricsSnapshot:
        if self._summary_cache is not None:
            cached = await self._summary_cache.read()
            if cached is not None:
                return await self._summary_cache.snapshot(cached)
            summary = await self._collector.collect_summary()
            await self._summary_cache.write(summary)
            return await self._summary_cache.snapshot(summary)
        return await self._collector.collect()

    async def prometheus(self) -> str:
        return self._prometheus.export(await self.snapshot())
