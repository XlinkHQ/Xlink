from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

from app.domain.client_assignment import ClientAssignment
from app.domain.node import Node
from app.domain.profile import Profile
from app.providers.base.models import ProviderKind

SUPPORTED_SUBSCRIPTION_PROTOCOLS = frozenset({"vless", "vmess", "trojan"})


@dataclass(frozen=True, slots=True)
class SubscriptionSource:
    assignment: ClientAssignment
    profile: Profile
    node: Node


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    assignment_id: uuid.UUID
    user_id: uuid.UUID
    provider_kind: ProviderKind
    provider_name: str
    protocol: str
    client_id: str
    email: str | None
    inbound_tag: str
    host: str
    port: int
    expires_at: datetime | None
    traffic_limit_bytes: int | None
    settings: Mapping[str, Any]

    @classmethod
    def build(
        cls,
        *,
        source: SubscriptionSource,
        provider_name: str,
        settings: dict[str, Any],
    ) -> ProviderConfig:
        assignment = source.assignment
        profile = source.profile
        node = source.node
        return cls(
            assignment_id=assignment.id,
            user_id=assignment.user_id,
            provider_kind=assignment.provider_kind,
            provider_name=provider_name,
            protocol=profile.protocol.strip().lower(),
            client_id=assignment.provider_client_id or str(assignment.id),
            email=str(settings.get("email", "")) or None,
            inbound_tag=profile.slug,
            host=node.host,
            port=node.port,
            expires_at=assignment.expires_at,
            traffic_limit_bytes=assignment.traffic_limit_bytes,
            settings=MappingProxyType(dict(settings)),
        )


@dataclass(frozen=True, slots=True)
class RenderedConfig:
    config: ProviderConfig
    uri: str
    version: str


@dataclass(frozen=True, slots=True)
class RenderedFeed:
    configs: tuple[RenderedConfig, ...]
    content: str
    version: str
    content_hash: str
    etag: str
    expires_at: datetime | None
