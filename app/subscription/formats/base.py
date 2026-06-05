from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import quote, urlencode

from app.core.exceptions import ValidationError
from app.subscription.models import ProviderConfig


class FormatRenderError(ValidationError):
    code = "subscription_format_error"
    message = "Subscription format rendering failed."


class UriRenderer(Protocol):
    protocol: str

    def render(self, config: ProviderConfig) -> str: ...


class FeedRenderer(Protocol):
    def render(self, configs: tuple[ProviderConfig, ...]) -> str: ...


def require_protocol(config: ProviderConfig, expected: str) -> None:
    if config.protocol != expected:
        raise FormatRenderError(
            f"Config protocol '{config.protocol}' is not '{expected}'.",
            code="subscription_protocol_mismatch",
            details={"expected": expected, "actual": config.protocol},
        )


def require_fields(config: ProviderConfig, fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if not _present(config, field)]
    if missing:
        raise FormatRenderError(
            f"Config is missing required fields: {missing}.",
            code="subscription_missing_fields",
            details={"missing": missing},
        )


def _present(config: ProviderConfig, field: str) -> bool:
    if field in ("host", "port", "client_id"):
        value = getattr(config, field, None)
        return value not in (None, "", 0)
    return config.settings.get(field) not in (None, "")


def validate_node(config: ProviderConfig) -> None:
    if not config.host or not str(config.host).strip():
        raise FormatRenderError("Config node host is missing.", code="subscription_invalid_node")
    if not isinstance(config.port, int) or config.port <= 0 or config.port > 65535:
        raise FormatRenderError(
            "Config node port is invalid.",
            code="subscription_invalid_node",
            details={"port": config.port},
        )


def label(config: ProviderConfig, *, encoded: bool = True) -> str:
    raw = f"{config.provider_name}-{config.inbound_tag}-{config.assignment_id}"
    return quote(raw) if encoded else raw


def query(values: dict[str, Any]) -> str:
    cleaned = {key: str(value) for key, value in values.items() if value not in (None, "")}
    return urlencode(cleaned)


def setting(config: ProviderConfig, key: str, default: Any = "") -> Any:
    value = config.settings.get(key, default)
    return value if value is not None else default
