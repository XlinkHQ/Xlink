from __future__ import annotations

from typing import Any

from app.core.exceptions import ValidationError
from app.providers.base.models import ProviderKind


def _require(settings: dict[str, Any], key: str, label: str) -> None:
    value = settings.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValidationError(f"{label} is required.", code="profile_settings_invalid")


def _port(settings: dict[str, Any]) -> None:
    port = settings.get("port")
    if port is None:
        return
    try:
        p = int(port)
    except (TypeError, ValueError) as exc:
        raise ValidationError("port must be a number.", code="profile_settings_invalid") from exc
    if not (1 <= p <= 65535):
        raise ValidationError("port must be between 1 and 65535.", code="profile_settings_invalid")


def _validate_security(settings: dict[str, Any]) -> None:
    security = str(settings.get("security", "none")).strip().lower()
    if security == "tls":
        if not (settings.get("sni") or settings.get("host")):
            raise ValidationError(
                "TLS requires an SNI (server name).", code="profile_settings_invalid"
            )
    elif security == "reality":
        if not (settings.get("publicKey") or settings.get("pbk")):
            raise ValidationError(
                "REALITY requires a publicKey.", code="profile_settings_invalid"
            )
        if not settings.get("sni"):
            raise ValidationError(
                "REALITY requires an SNI (server name).", code="profile_settings_invalid"
            )


def _validate_singbox(protocol: str, settings: dict[str, Any]) -> None:
    _port(settings)
    _validate_security(settings)
    if protocol == "hysteria2" and not (settings.get("password") or settings.get("obfs")):
        return


def _validate_hysteria(protocol: str, settings: dict[str, Any]) -> None:
    _port(settings)
    if not (settings.get("sni") or settings.get("host") or settings.get("obfs")):
        return


def _validate_wireguard(protocol: str, settings: dict[str, Any]) -> None:
    _port(settings)
    _require(settings, "address", "Interface address")


_VALIDATORS = {
    ProviderKind.SING_BOX: _validate_singbox,
    ProviderKind.HYSTERIA: _validate_hysteria,
    ProviderKind.WIREGUARD: _validate_wireguard,
}


def validate_profile_settings(
    kind: ProviderKind, protocol: str, settings: dict[str, Any] | None
) -> None:
    validator = _VALIDATORS.get(kind)
    if validator is None:
        return
    validator(str(protocol or "").strip().lower(), settings or {})
