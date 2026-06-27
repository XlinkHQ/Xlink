from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.traffic.repository import TrafficRepository

logger = get_logger("xlink.traffic.retention")


class TrafficRetention:
    def __init__(self, session: AsyncSession, *, retention_days: int) -> None:
        self._repo = TrafficRepository(session)
        self._retention_days = max(1, retention_days)

    def cutoff(self, now: datetime | None = None) -> datetime:
        reference = now or datetime.now(UTC)
        return reference - timedelta(days=self._retention_days)

    async def purge(self, now: datetime | None = None) -> int:
        cutoff = self.cutoff(now)
        byte_sums = await self._repo.sum_bytes_before(cutoff)
        deleted = await self._repo.delete_before(cutoff)
        if byte_sums:
            reduction = {aid: -total for aid, total in byte_sums.items()}
            await self._repo.apply_usage_deltas(reduction)
            await self._repo.resync_user_usage_for_assignments(list(byte_sums))
        if deleted:
            logger.info("traffic_purged", deleted=deleted, cutoff=cutoff.isoformat())
        return deleted
