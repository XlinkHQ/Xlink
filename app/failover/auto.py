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
        cache=None,  # noqa: ANN001
    ) -> None:
        self._service = service
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._recent: dict[uuid.UUID, float] = {}
        # With several replicas (or after a leader handover) a process-local
        # cooldown lets the same outage trigger failover more than once. A
        # Redis SET NX makes the cooldown cluster-wide.
        self._cache = cache

    async def __call__(self, event: DomainEvent) -> None:
        if not isinstance(event, NodeOffline):
            return
        if self._cache is not None:
            try:
                # redis-py returns None (not False) when NX loses.
                claimed = bool(
                    await self._cache.client.set(
                        f"failover:cooldown:{event.node_id}",
                        "1",
                        nx=True,
                        ex=max(1, int(self._cooldown)),
                    )
                )
            except Exception:
                claimed = True  # Redis down: fall back to the local cooldown
            if not claimed:
                logger.info("auto_failover_skipped_cooldown", node_id=str(event.node_id))
                return
        now = self._clock()
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
