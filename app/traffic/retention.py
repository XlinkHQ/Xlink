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
        # Purge only the historical record rows. used_bytes/users_data_usage are
        # monotonic enforcement counters (incremented at ingest, zeroed only by
        # explicit resets) and must NOT be reduced when old history is trimmed,
        # otherwise a data-limited user silently regains quota over time.
        cutoff = self.cutoff(now)
        deleted = await self._repo.delete_before(cutoff)
        if deleted:
            logger.info("traffic_purged", deleted=deleted, cutoff=cutoff.isoformat())
        return deleted
