from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.providers.base.models import ProviderKind


def _event_id() -> uuid.UUID:
    return uuid.uuid4()


def _occurred_at() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    event_id: uuid.UUID = field(default_factory=_event_id)
    occurred_at: datetime = field(default_factory=_occurred_at)
    correlation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def event_name(self) -> str:
        return type(self).__name__


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignmentCreated(DomainEvent):
    assignment_id: uuid.UUID
    user_id: uuid.UUID
    profile_id: uuid.UUID
    node_id: uuid.UUID
    provider_kind: ProviderKind


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignmentDisabled(DomainEvent):
    assignment_id: uuid.UUID
    user_id: uuid.UUID
    provider_kind: ProviderKind


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignmentExpired(DomainEvent):
    assignment_id: uuid.UUID
    user_id: uuid.UUID
    expired_at: datetime
    provider_kind: ProviderKind


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeOffline(DomainEvent):
    node_id: uuid.UUID
    reason: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeRecovered(DomainEvent):
    node_id: uuid.UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderUnavailable(DomainEvent):
    provider_kind: ProviderKind
    reason: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class TrafficLimitReached(DomainEvent):
    assignment_id: uuid.UUID
    user_id: uuid.UUID
    limit_bytes: int
    used_bytes: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SubscriptionGenerated(DomainEvent):
    scope: str
    subject_id: uuid.UUID
    content_hash: str
    etag: str
    item_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeCommandIssued(DomainEvent):
    command_id: uuid.UUID
    node_id: uuid.UUID
    kind: str
    origin: str


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeProviderUnhealthy(DomainEvent):
    node_id: uuid.UUID
    provider_name: str
    status: str
    detail: str | None = None
