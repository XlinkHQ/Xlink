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
from app.protocols import subscription_protocols
from app.providers.base.models import ProviderKind

SUPPORTED_SUBSCRIPTION_PROTOCOLS = subscription_protocols()


def _strip_port(host: str) -> str:
    host = host.strip()
    if host.startswith("["):
        return host[1 : host.index("]")] if "]" in host else host.strip("[]")
    if host.count(":") == 1:
        return host.rsplit(":", 1)[0]
    return host


def _resolve_host(protocol: str, settings: Mapping[str, Any], node_host: str) -> str:
    if protocol == "wireguard":
        host = settings.get("endpoint") or settings.get("host") or node_host
    else:
        host = settings.get("address") or node_host
    host = str(host).split("/", 1)[0].strip()
    host = _strip_port(host)
    for ch in ("@", "?", "#", " ", "\t", "\r", "\n"):
        host = host.replace(ch, "")
    return host


_DEFAULT_PORT: dict[str, int] = {"wireguard": 51820}


def _resolve_port(protocol: str, settings: Mapping[str, Any], node_port: int) -> int:
    port = settings.get("port")
    if port:
        from app.core.exceptions import ValidationError

        try:
            return int(port)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                f"Profile port must be an integer, got {port!r}.",
                code="subscription_invalid_port",
            ) from exc
    return _DEFAULT_PORT.get(protocol, node_port)


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
        user = assignment.user

        expires_at = assignment.expires_at or getattr(user, "expire_at", None)
        data_limit = assignment.traffic_limit_bytes or getattr(user, "data_limit_bytes", None)
        return cls(
            assignment_id=assignment.id,
            user_id=assignment.user_id,
            provider_kind=assignment.provider_kind,
            provider_name=provider_name,
            protocol=profile.protocol.strip().lower(),
            client_id=assignment.provider_client_id or str(assignment.id),
            email=str(settings.get("email", "")) or None,
            inbound_tag=profile.slug,
            host=_resolve_host(profile.protocol.strip().lower(), settings, node.host),
            port=_resolve_port(profile.protocol.strip().lower(), settings, node.port),
            expires_at=expires_at,
            traffic_limit_bytes=data_limit,
            settings=MappingProxyType(dict(settings)),
        )

    @property
    def resolved_uuid(self) -> str:
        value = self.settings.get("uuid")
        if value not in (None, ""):
            return str(value)
        return self.client_id

    @property
    def resolved_password(self) -> str:
        value = self.settings.get("password")
        if value not in (None, ""):
            return str(value)
        return self.client_id


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
