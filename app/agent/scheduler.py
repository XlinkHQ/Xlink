from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.agent.heartbeat import NodeHeartbeatService
from app.core.leader import LeaderElector
from app.core.logging import get_logger
from app.db.session import Database
from app.domain.node import Node, NodeStatus
from app.events.bus import EventBus
from app.repositories.node import NodeRepository
from app.webhooks.dispatcher import WebhookDispatcher

logger = get_logger("xlink.agent.scheduler")


class NodeAgentScheduler:
    def __init__(
        self,
        db: Database,
        *,
        events: EventBus | None = None,
        dispatcher: WebhookDispatcher | None = None,
        interval_seconds: int = 30,
        offline_after_seconds: int = 90,
        leader: LeaderElector | None = None,
    ) -> None:
        self._db = db
        self._events = events
        self._dispatcher = dispatcher
        self._interval = interval_seconds
        self._offline_after = offline_after_seconds
        self._leader = leader
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="node-agent-scheduler")
        logger.info(
            "node_agent_scheduler_started",
            interval_seconds=self._interval,
            offline_after_seconds=self._offline_after,
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
        logger.info("node_agent_scheduler_stopped")

    async def detect_offline_once(self) -> int:
        async with self._db.session() as session:
            threshold = datetime.now(UTC) - timedelta(seconds=self._offline_after)
            stmt = select(Node).where(
                Node.status == NodeStatus.ACTIVE,
                Node.last_seen_at.is_not(None),
                Node.last_seen_at < threshold,
            )
            nodes = (await session.execute(stmt)).scalars().all()
            heartbeat = NodeHeartbeatService(
                NodeRepository(session), self._events, self._dispatcher
            )
            for node in nodes:
                await heartbeat.mark_stale_offline(node)
            return len(nodes)

    async def _run(self) -> None:
        while not self._stopping.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            if self._stopping.is_set():
                break
            if self._leader is not None and not self._leader.is_leader:
                continue
            try:
                offline = await self.detect_offline_once()
                if offline:
                    logger.info("nodes_marked_offline", count=offline)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("node_agent_scheduler_failed")
