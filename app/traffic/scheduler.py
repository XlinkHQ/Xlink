from __future__ import annotations

import asyncio
import contextlib

from app.core.logging import get_logger
from app.db.session import Database
from app.traffic.retention import TrafficRetention
from app.traffic.service import TrafficService

logger = get_logger("xlink.traffic.scheduler")


async def run_retention(
    db: Database, *, retention_days: int, raw_retention_days: int | None = None
) -> int:
    async with db.session() as session:
        retention = TrafficRetention(
            session, retention_days=retention_days, raw_retention_days=raw_retention_days
        )
        return await retention.purge()


async def run_rollup(db: Database) -> int:
    async with db.session() as session:
        return await TrafficService(session).rollup_hourly()


class TrafficRetentionJob:
    def __init__(
        self,
        db: Database,
        *,
        interval_seconds: int,
        retention_days: int,
        raw_retention_days: int | None = None,
        leader=None,
    ) -> None:
        self._db = db
        self._interval = interval_seconds
        self._retention_days = retention_days
        self._raw_retention_days = raw_retention_days
        self._leader = leader
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="traffic-retention")
        logger.info(
            "traffic_retention_started",
            interval_seconds=self._interval,
            retention_days=self._retention_days,
        )

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
        logger.info("traffic_retention_stopped")

    async def _run(self) -> None:
        while not self._stopping.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            if self._stopping.is_set():
                break
            if self._leader is not None and not self._leader.is_leader:
                continue
            try:
                await run_retention(
                    self._db,
                    retention_days=self._retention_days,
                    raw_retention_days=self._raw_retention_days,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("traffic_retention_failed")


class TrafficRollupJob:
    """Periodically compacts raw traffic_records into the hourly rollup table.
    Leader-gated like the retention job so only one worker rolls up. The rollup
    is idempotent (ON CONFLICT recompute), so a missed/overlapping run is safe."""

    def __init__(self, db: Database, *, interval_seconds: int, leader=None) -> None:
        self._db = db
        self._interval = interval_seconds
        self._leader = leader
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="traffic-rollup")
        logger.info("traffic_rollup_started", interval_seconds=self._interval)

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
        logger.info("traffic_rollup_stopped")

    async def _run(self) -> None:
        while not self._stopping.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            if self._stopping.is_set():
                break
            if self._leader is not None and not self._leader.is_leader:
                continue
            try:
                await run_rollup(self._db)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("traffic_rollup_failed")
