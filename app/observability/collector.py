from __future__ import annotations

import asyncio
import contextlib

from sqlalchemy import func, select

from app.core.logging import get_logger
from app.db.session import Database
from app.domain.node import Node, NodeStatus
from app.domain.user import User
from app.observability.prometheus import PrometheusMetrics

logger = get_logger("xlink.observability.collector")


class DomainMetricsCollector:
    """Refreshes the domain gauges on an interval — NOT on every scrape.

    The scrape handler only serializes in-memory gauge values (cheap, no I/O).
    This job runs the small aggregate COUNT/SUM queries in the background at a
    fixed cadence and mirrors the results into the gauges, so a burst of
    scrapes cannot translate into a burst of DB load. Leader-gated so N
    replicas don't each run the same counts.
    """

    def __init__(
        self,
        db: Database,
        metrics: PrometheusMetrics,
        *,
        interval_seconds: int = 30,
        leader=None,
    ) -> None:
        self._db = db
        self._metrics = metrics
        self._interval = max(5, interval_seconds)
        self._leader = leader
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="metrics-domain-collector")
        logger.info("domain_metrics_collector_started", interval_seconds=self._interval)

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
        logger.info("domain_metrics_collector_stopped")

    def _is_leader(self) -> bool:
        return self._leader is None or self._leader.is_leader

    async def refresh(self) -> None:
        """Run the cheap aggregate counts and mirror them into the gauges."""
        async with self._db.session() as session:
            users_total = await session.scalar(select(func.count()).select_from(User))
            users_active = await session.scalar(
                select(func.count()).select_from(User).where(User.is_active.is_(True))
            )
            nodes_total = await session.scalar(select(func.count()).select_from(Node))
            nodes_online = await session.scalar(
                select(func.count()).select_from(Node).where(Node.status == NodeStatus.ACTIVE)
            )
            assignments_active, traffic_bytes = await self._assignments_and_traffic(session)

        self._metrics.users_total.set(float(users_total or 0))
        self._metrics.users_active.set(float(users_active or 0))
        self._metrics.nodes_total.set(float(nodes_total or 0))
        self._metrics.nodes_online.set(float(nodes_online or 0))
        self._metrics.assignments_active.set(float(assignments_active or 0))
        self._metrics.traffic_bytes_total.set(float(traffic_bytes or 0))
        self._metrics.domain_metrics_up.set(1.0)

    async def _assignments_and_traffic(self, session) -> tuple[int, float]:
        from app.domain.client_assignment import AssignmentStatus, ClientAssignment
        from app.traffic.repository import TrafficRepository

        assignments_active = await session.scalar(
            select(func.count())
            .select_from(ClientAssignment)
            .where(ClientAssignment.status == AssignmentStatus.ACTIVE)
        )
        totals = await TrafficRepository(session).totals()
        return int(assignments_active or 0), float(totals.total_bytes)

    async def _run(self) -> None:
        if self._is_leader():
            with contextlib.suppress(Exception):
                await self.refresh()
        while not self._stopping.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            if self._stopping.is_set():
                break
            if not self._is_leader():
                continue
            try:
                await self.refresh()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("domain_metrics_refresh_failed")
