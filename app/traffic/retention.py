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
        # retention_days governs the ROLLUP horizon (full analytics window, e.g.
        # 90d). raw_retention_days is the shorter horizon after which raw
        # per-sample rows are dropped — they only exist for sub-hour/live
        # precision, which is no longer needed once a bucket is rolled up.
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
        # Purge only the historical record rows. used_bytes/users_data_usage are
        # monotonic enforcement counters (incremented at ingest, zeroed only by
        # explicit resets) and must NOT be reduced when old history is trimmed,
        # otherwise a data-limited user silently regains quota over time.
        #
        # Raw rows are dropped at the SHORTER raw cutoff, but never past the
        # rollup watermark: deleting a raw row for an hour not yet rolled up
        # would lose that usage from analytics entirely. The rollup rows carry
        # the history for the full retention window; they are purged at the
        # longer cutoff.
        rollup_cutoff = self.cutoff(now)
        raw_cutoff = self.raw_cutoff(now)
        watermark = await self._repo.get_rollup_watermark()
        # The protective frontier is the point up to which raw is safe to drop
        # because a durable copy exists beyond it. With rollups, that's the
        # watermark (everything before it is in traffic_hourly). With NO rollups
        # yet (watermark NULL), the only durable horizon is the full retention
        # cutoff — beyond it, history is discarded by design, so raw there may
        # go regardless; within it, raw is the sole copy and must be kept.
        frontier = watermark if watermark is not None else rollup_cutoff
        # Drop raw older than the (shorter) raw cutoff, but never past the
        # frontier — that would erase usage not yet rolled up.
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
