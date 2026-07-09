from __future__ import annotations

import uuid
from collections.abc import Callable
from time import monotonic

from app.core.logging import get_logger
from app.events.models import DomainEvent, NodeOffline
from app.failover.service import FailoverService

logger = get_logger("xlink.failover.auto")


Clock = Callable[[], float]


class AutoFailoverHandler:
    def __init__(
        self,
        service: FailoverService,
        *,
        cooldown_seconds: float,
        clock: Clock = monotonic,
    ) -> None:
        self._service = service
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._recent: dict[uuid.UUID, float] = {}

    async def __call__(self, event: DomainEvent) -> None:
        if not isinstance(event, NodeOffline):
            return
        now = self._clock()
        # Drop cooldown entries that have expired so the map can't grow unbounded
        # with one row per node ever seen offline over the process lifetime.
        expired = [nid for nid, t in self._recent.items() if now - t >= self._cooldown]
        for nid in expired:
            del self._recent[nid]
        last = self._recent.get(event.node_id)
        if last is not None and now - last < self._cooldown:
            logger.info("auto_failover_skipped_cooldown", node_id=str(event.node_id))
            return
        self._recent[event.node_id] = now
        try:
            result = await self._service.failover_node(event.node_id)
            logger.info(
                "auto_failover_executed",
                node_id=str(event.node_id),
                migrated=result.migrated,
                skipped=result.skipped,
            )
        except Exception:
            logger.exception("auto_failover_failed", node_id=str(event.node_id))
