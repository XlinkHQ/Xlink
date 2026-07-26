from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlencode

from app.core.exceptions import ValidationError
from app.subscription.models import ProviderConfig


def format_bytes(
    num: float,
    *,
    units: tuple[str, ...] = ("B", "KiB", "MiB", "GiB", "TiB"),
    precision: int = 1,
    sep: str = "",
) -> str:
    value = float(num)
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024
        index += 1
    digits = 0 if index == 0 else precision
    return f"{value:.{digits}f}{sep}{units[index]}"


def _bytes(v: int) -> str:
    return format_bytes(v)


def _remark_vars(config: ProviderConfig) -> dict[str, str]:
    expire_date = ""
    days_left = ""
    if config.expires_at is not None:
        exp = (
            config.expires_at if config.expires_at.tzinfo else config.expires_at.replace(tzinfo=UTC)
        )
        expire_date = exp.strftime("%Y-%m-%d")
        days_left = str(max(0, (exp - datetime.now(UTC)).days))

    resolved = config.settings.get("_vars")
    if isinstance(resolved, dict):
        return {**resolved, "EXPIRE_DATE": expire_date}
    return {
        "USERNAME": str(config.email or ""),
        "PROTOCOL": config.protocol,
        "TRANSPORT": str(config.settings.get("network", "tcp")),
        "EXPIRE_DATE": expire_date,
        "DAYS_LEFT": days_left,
        "DATA_LIMIT": _bytes(config.traffic_limit_bytes) if config.traffic_limit_bytes else "∞",
    }


class FormatRenderError(ValidationError):
    code = "subscription_format_error"
    message = "Subscription format rendering failed."


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

    raw = str(
        config.settings.get("remark")
        or config.settings.get("display_name")
        or config.inbound_tag
        or config.provider_name
    )
    for key, value in _remark_vars(config).items():
        raw = raw.replace(f"{{{key}}}", value)
    return quote(raw) if encoded else raw


def query(values: dict[str, Any]) -> str:
    cleaned = {key: str(value) for key, value in values.items() if value not in (None, "")}
    return urlencode(cleaned)


def setting(config: ProviderConfig, key: str, default: Any = "") -> Any:
    value = config.settings.get(key, default)
    return value if value is not None else default


def normalize_alpn(config: ProviderConfig, key: str = "alpn") -> list[str]:
    value = config.settings.get(key)
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def setting_int(config: ProviderConfig, key: str, default: int = 0) -> int:
    """Coerce a numeric setting, turning bad data into a per-config skip.

    A stored non-numeric value (e.g. alterId="x") must NOT crash the whole feed
    with a raw ValueError — the renderers only catch FormatRenderError, and the
    public /sub endpoint would otherwise 500. Raising FormatRenderError here lets
    the per-config loop skip just that entry.
    """
    value = config.settings.get(key, default)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise FormatRenderError(
            f"Setting '{key}' must be an integer, got {value!r}.",
            code="subscription_setting_not_int",
            details={"setting": key},
        ) from exc
