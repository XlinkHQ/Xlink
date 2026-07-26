from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.traffic.repository import TrafficRepository

logger = get_logger("xlink.traffic.retention")


class TrafficRetention:
    def __init__(
        self,
        session: AsyncSession,
        *,
        retention_days: int,
        raw_retention_days: int | None = None,
    ) -> None:
        self._repo = TrafficRepository(session)
        self._retention_days = max(1, retention_days)
        raw = raw_retention_days if raw_retention_days is not None else retention_days
        self._raw_retention_days = min(max(1, raw), self._retention_days)

    def cutoff(self, now: datetime | None = None) -> datetime:
        reference = now or datetime.now(UTC)
        return reference - timedelta(days=self._retention_days)

    def raw_cutoff(self, now: datetime | None = None) -> datetime:
        reference = now or datetime.now(UTC)
        return reference - timedelta(days=self._raw_retention_days)

    async def purge(self, now: datetime | None = None) -> int:
        rollup_cutoff = self.cutoff(now)
        raw_cutoff = self.raw_cutoff(now)
        watermark = await self._repo.get_rollup_watermark()
        frontier = watermark if watermark is not None else rollup_cutoff
        effective_raw_cutoff = min(raw_cutoff, frontier)
        deleted = await self._repo.delete_before(effective_raw_cutoff)
        rolled = await self._repo.delete_hourly_before(rollup_cutoff)
        if deleted or rolled:
            logger.info(
                "traffic_purged",
                deleted=deleted,
                rolled_deleted=rolled,
                raw_cutoff=raw_cutoff.isoformat(),
                rollup_cutoff=rollup_cutoff.isoformat(),
            )
        return deleted
