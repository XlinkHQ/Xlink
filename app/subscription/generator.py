from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.domain.client_assignment import AssignmentStatus
from app.domain.node import NodeStatus
from app.providers.base.exceptions import ProviderNotFoundError
from app.providers.base.models import ProviderKind
from app.providers.base.registry import ProviderRegistry
from app.subscription.formats.base import format_bytes
from app.subscription.models import (
    SUPPORTED_SUBSCRIPTION_PROTOCOLS,
    ProviderConfig,
    SubscriptionSource,
)

_log = get_logger("xlink.subscription.generator")

_CREDENTIAL_KEY_ALIASES = {
    "private_key": "privateKey",
    "server_public_key": "peerPublicKey",
    "preshared_key": "presharedKey",
    "obfs_password": "obfsPassword",
}


def _credential_settings(credentials: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, value in credentials.items():
        merged[key] = value
        alias = _CREDENTIAL_KEY_ALIASES.get(key)
        if alias is not None:
            merged[alias] = value
    return merged


_PROTO_NAMES = {
    "vless": "VLESS",
    "vmess": "VMess",
    "trojan": "Trojan",
    "shadowsocks": "Shadowsocks",
    "shadowsocks2022": "Shadowsocks 2022",
    "shadowtls": "ShadowTLS",
    "hysteria2": "Hysteria2",
    "tuic": "TUIC",
    "anytls": "AnyTLS",
    "wireguard": "WireGuard",
}


def _human(num: int | None) -> str:
    if num is None:
        return "∞"
    return format_bytes(num, units=("B", "KB", "MB", "GB", "TB"), precision=1, sep="")


def _substitute(text: str, variables: dict[str, str]) -> str:
    for key, value in variables.items():
        text = text.replace(f"{{{key}}}", value)
    return text


DEFAULT_STATUS_TEXTS = {
    "active": "Active",
    "expired": "Expired",
    "limited": "Limited",
    "disabled": "Disabled",
    "onhold": "On-Hold",
}


def _user_status(
    user: Any, used: int, limit: int | None, texts: dict[str, str] | None = None
) -> tuple[str, str]:
    t = texts or DEFAULT_STATUS_TEXTS
    if getattr(user, "on_hold", False):
        deadline = getattr(user, "activation_deadline", None)
        if deadline is not None:
            dl = deadline if deadline.tzinfo else deadline.replace(tzinfo=UTC)
            if dl < datetime.now(UTC):
                return (t.get("expired", "Expired"), "⌛️")
        return (t.get("onhold", "On-Hold"), "⏳")
    if not getattr(user, "is_active", True):
        return (t.get("disabled", "Disabled"), "🔴")
    expire = getattr(user, "expire_at", None)
    if expire is not None:
        exp = expire if expire.tzinfo else expire.replace(tzinfo=UTC)
        if exp < datetime.now(UTC):
            return (t.get("expired", "Expired"), "⌛️")
    if limit is not None and used >= limit:
        return (t.get("limited", "Limited"), "🪫")
    return (t.get("active", "Active"), "✅")


def _seed(user_id: uuid.UUID) -> str:
    return hashlib.sha256(str(user_id).encode()).hexdigest()


def _apply_host_dynamics(settings: dict[str, Any], user_id: uuid.UUID) -> dict[str, Any]:
    digest = _seed(user_id)
    sub = digest[:10]
    out = dict(settings)
    for key in ("address", "sni", "host"):
        value = out.get(key)
        if not isinstance(value, str) or not value:
            continue
        if "," in value:
            options = [v.strip() for v in value.split(",") if v.strip()]
            if options:
                value = options[int(digest[:8], 16) % len(options)]
        if "*" in value:
            value = value.replace("*", sub)
        out[key] = value
    return out


class SubscriptionGenerator:
    def __init__(self, providers: ProviderRegistry) -> None:
        self._providers = providers

    async def generate_config(self, source: SubscriptionSource) -> ProviderConfig:
        return self._build_config(source)

    async def generate_feed(
        self,
        sources: tuple[SubscriptionSource, ...],
        status_texts: dict[str, str] | None = None,
        host_overrides: dict[uuid.UUID, list[dict[str, Any]]] | None = None,
    ) -> tuple[ProviderConfig, ...]:
        configs: list[ProviderConfig] = []

        for source in sources:
            user = source.assignment.user
            used_total = int(getattr(user, "users_data_usage", 0) or 0)
            if used_total == 0:
                used_total = int(source.assignment.used_bytes or 0)
            try:
                configs.extend(
                    self._build_configs(source, used_total, status_texts, host_overrides)
                )
            except ValidationError as exc:
                _log.info(
                    "subscription_source_skipped",
                    assignment_id=str(getattr(source.assignment, "id", "")),
                    reason=str(exc),
                )
                continue

        return tuple(configs)

    def _base_settings(
        self, source: SubscriptionSource, used_total: int, texts: dict[str, str] | None = None
    ) -> dict[str, Any]:
        user = source.assignment.user
        if source.assignment.traffic_limit_bytes:
            limit = source.assignment.traffic_limit_bytes
            used_total = int(source.assignment.used_bytes or 0)
        else:
            limit = getattr(user, "data_limit_bytes", None)
        status_text, status_emoji = _user_status(user, used_total, limit, texts)
        expire = getattr(user, "expire_at", None)
        days_left = ""
        if expire is not None:
            exp = expire if expire.tzinfo else expire.replace(tzinfo=UTC)
            days_left = str(max(0, (exp - datetime.now(UTC)).days))
        proto = source.profile.protocol.strip().lower()
        variables = {
            "SERVER_IP": source.node.host,
            "USERNAME": user.email or user.username,
            "DATA_USAGE": _human(used_total),
            "DATA_LEFT": _human(max(0, limit - used_total)) if limit is not None else "∞",
            "DATA_LIMIT": _human(limit) if limit is not None else "∞",
            "DAYS_LEFT": days_left,
            "STATUS_TEXT": status_text,
            "STATUS_EMOJI": status_emoji,
            "PROTOCOL": _PROTO_NAMES.get(proto, proto.upper()),
            "TRANSPORT": str(source.profile.settings.get("network", "tcp")),
        }
        base = {
            **source.profile.settings,
            **_credential_settings(source.assignment.credentials),
            "assignment_id": str(source.assignment.id),
            "profile_slug": source.profile.slug,
            "node_slug": source.node.slug,
            "display_name": source.profile.name,
            "email": user.email or user.username,
            "_vars": variables,
        }

        global_remark = (texts or {}).get("remark")
        if global_remark and not base.get("remark"):
            base["remark"] = global_remark

        if source.profile.protocol.strip().lower() == "wireguard":
            creds = source.assignment.credentials or {}
            client_addr = creds.get("address") if isinstance(creds, dict) else None
            if client_addr:
                base["address"] = str(client_addr)
            else:
                base.pop("address", None)
        return base

    def _build_configs(
        self,
        source: SubscriptionSource,
        used_total: int = 0,
        texts: dict[str, str] | None = None,
        host_overrides: dict[uuid.UUID, list[dict[str, Any]]] | None = None,
    ) -> list[ProviderConfig]:
        self._validate_source(source)
        provider = self._get_provider(source.assignment.provider_kind)
        base = self._base_settings(source, used_total, texts)
        is_wireguard = source.profile.protocol.strip().lower() == "wireguard"
        hosts: Any = None
        if host_overrides and not is_wireguard:
            hosts = host_overrides.get(source.profile.id)
        if not hosts and not is_wireguard:
            hosts = source.profile.settings.get("hosts")
        if not isinstance(hosts, list) or not hosts:
            return [ProviderConfig.build(source=source, provider_name=provider.name, settings=base)]

        variables = base.get("_vars", {})
        configs: list[ProviderConfig] = []
        for host in hosts:
            if not isinstance(host, dict):
                continue
            merged = dict(base)
            merged.update({k: v for k, v in host.items() if v not in (None, "")})

            if isinstance(merged.get("address"), str):
                merged["address"] = _substitute(merged["address"], variables)
            merged = _apply_host_dynamics(merged, source.assignment.user_id)
            configs.append(
                ProviderConfig.build(source=source, provider_name=provider.name, settings=merged)
            )
        return configs

    def _build_config(self, source: SubscriptionSource) -> ProviderConfig:
        return self._build_configs(source)[0]

    def _validate_source(self, source: SubscriptionSource) -> None:
        assignment = source.assignment
        profile = source.profile
        node = source.node

        if assignment.provider_kind != profile.provider_kind:
            raise ValidationError(
                "Assignment provider does not match profile provider.",
                code="subscription_provider_mismatch",
            )
        if assignment.status is not AssignmentStatus.ACTIVE:
            raise ValidationError(
                "Assignment is disabled.", code="subscription_assignment_disabled"
            )
        if not profile.is_active:
            raise ValidationError("Profile is disabled.", code="subscription_profile_disabled")

        if node.status is NodeStatus.DISABLED:
            raise ValidationError("Node is disabled.", code="subscription_node_disabled")

        expires_at = assignment.expires_at
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= datetime.now(UTC):
                raise ValidationError(
                    "Assignment is expired.", code="subscription_assignment_expired"
                )

        if (
            assignment.traffic_limit_bytes is not None
            and (assignment.used_bytes or 0) >= assignment.traffic_limit_bytes
        ):
            raise ValidationError(
                "Assignment is over its traffic limit.",
                code="subscription_assignment_over_limit",
            )

        protocol = profile.protocol.strip().lower()
        if protocol not in SUPPORTED_SUBSCRIPTION_PROTOCOLS:
            raise ValidationError(
                "Profile protocol is not supported for subscriptions.",
                code="subscription_protocol_unsupported",
                details={"protocol": profile.protocol},
            )

        self._get_provider(profile.provider_kind)

    def _get_provider(self, provider_kind: ProviderKind):
        try:
            return self._providers.get_by_kind(provider_kind)
        except ProviderNotFoundError as exc:
            raise ValidationError(
                "Provider is not registered.",
                code="subscription_provider_unavailable",
                details={"provider_kind": provider_kind.value},
            ) from exc
