from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.domain import NodeProviderHealth, ProviderHealthStatus
from app.agent.repository import NodeProviderHealthRepository
from app.core.logging import get_logger
from app.events.bus import EventBus
from app.events.models import NodeProviderUnhealthy

logger = get_logger("xlink.agent.provider_health")

_UNHEALTHY = (ProviderHealthStatus.DEGRADED, ProviderHealthStatus.UNHEALTHY)


class ProviderHealthService:
    def __init__(self, session: AsyncSession, *, events: EventBus | None = None) -> None:
        self._session = session
        self._repo = NodeProviderHealthRepository(session)
        self._events = events

    async def record(
        self,
        node_id: uuid.UUID,
        checks: Sequence[dict],
    ) -> int:
        now = datetime.now(UTC)
        records: list[NodeProviderHealth] = []
        unhealthy: list[NodeProviderHealth] = []
        for check in checks:
            status = self._coerce_status(check.get("status"))
            record = NodeProviderHealth(
                node_id=node_id,
                provider_name=str(check["provider_name"]),
                status=status,
                latency_ms=check.get("latency_ms"),
                detail=check.get("detail"),
                checked_at=now,
            )
            records.append(record)
            if status in _UNHEALTHY:
                unhealthy.append(record)
        count = await self._repo.add_all(records)
        if self._events is not None:
            for record in unhealthy:
                await self._events.publish(
                    NodeProviderUnhealthy(
                        node_id=node_id,
                        provider_name=record.provider_name,
                        status=record.status.value,
                        detail=record.detail,
                    )
                )
        if unhealthy:
            logger.info(
                "node_provider_unhealthy",
                node_id=str(node_id),
                count=len(unhealthy),
            )
        return count

    async def latest(self, node_id: uuid.UUID) -> Sequence[NodeProviderHealth]:
        return await self._repo.latest_for_node(node_id)

    def _coerce_status(self, value) -> ProviderHealthStatus:
        try:
            return ProviderHealthStatus(str(value))
        except ValueError:
            return ProviderHealthStatus.UNKNOWN
