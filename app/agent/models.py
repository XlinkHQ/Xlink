from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from app.domain.client_assignment import AssignmentStatus
from app.providers.base.models import ProviderKind


class AgentHealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class NodeStats:
    current_users: int
    cpu_percent: float | None = None
    memory_percent: float | None = None
    rx_bytes: int | None = None
    tx_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class AgentHeartbeat:
    node_id: uuid.UUID
    status: AgentHealthStatus = AgentHealthStatus.HEALTHY
    stats: NodeStats = field(default_factory=lambda: NodeStats(current_users=0))
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class AssignmentSyncItem:
    assignment_id: uuid.UUID
    user_id: uuid.UUID
    profile_id: uuid.UUID
    provider_kind: ProviderKind
    provider_client_id: str | None
    status: AssignmentStatus
    version: int
    updated_at: datetime
    settings: Mapping[str, Any]

    @classmethod
    def build(cls, **values: Any) -> AssignmentSyncItem:
        settings = MappingProxyType(dict(values.pop("settings", {})))
        return cls(settings=settings, **values)


@dataclass(frozen=True, slots=True)
class SyncCursor:
    updated_at: datetime
    assignment_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class SyncBatch:
    node_id: uuid.UUID
    items: tuple[AssignmentSyncItem, ...]
    next_cursor: SyncCursor | None
    has_more: bool


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.05
    max_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0

    def delay_for(self, attempt: int) -> float:
        if self.base_delay_seconds <= 0:
            return 0.0
        delay = self.base_delay_seconds * (self.backoff_multiplier ** max(0, attempt - 1))
        return min(delay, self.max_delay_seconds)
