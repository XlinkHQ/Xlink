from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.user import User
from app.monitoring.models import Metric, MetricsSnapshot
from app.providers.base.registry import ProviderRegistry
from app.traffic.repository import TrafficRepository

_SUMMARY_KEYS = (
    "active_users",
    "active_nodes",
    "offline_nodes",
    "active_assignments",
    "total_traffic_bytes",
)


async def snapshot_from_summary(
    summary: dict[str, float], providers: ProviderRegistry
) -> MetricsSnapshot:
    metrics = [Metric(key, float(summary.get(key, 0.0))) for key in _SUMMARY_KEYS]
    provs = list(providers.all())

    async def _check(provider: Any) -> bool:
        try:
            return await provider.health_check()
        except Exception:
            return False

    results = await asyncio.gather(*[_check(p) for p in provs]) if provs else []
    for provider, healthy in zip(provs, results, strict=False):
        meta = provider.metadata
        metrics.append(
            Metric(
                "provider_health",
                1.0 if healthy else 0.0,
                {"provider": meta.name, "kind": meta.kind.value},
            )
        )
    return MetricsSnapshot(metrics=tuple(metrics))


class MetricsCollector:
    def __init__(self, session: AsyncSession, providers: ProviderRegistry) -> None:
        self._session = session
        self._providers = providers

    async def collect(self) -> MetricsSnapshot:
        summary = await self.collect_summary()
        return await snapshot_from_summary(summary, self._providers)

    async def collect_summary(self) -> dict[str, float]:
        return {
            "active_users": await self._count(User, User.is_active.is_(True)),
            "active_nodes": await self._count(Node, Node.status == NodeStatus.ACTIVE),
            "offline_nodes": await self._count(Node, Node.status == NodeStatus.OFFLINE),
            "active_assignments": await self._count(
                ClientAssignment, ClientAssignment.status == AssignmentStatus.ACTIVE
            ),
            "total_traffic_bytes": await self._total_traffic_bytes(),
        }

    async def _count(self, model, *conditions) -> float:
        stmt = select(func.count()).select_from(model).where(*conditions)
        return float(await self._session.scalar(stmt) or 0)

    async def _total_traffic_bytes(self) -> float:
        totals = await TrafficRepository(self._session).totals()
        return float(totals.total_bytes)
