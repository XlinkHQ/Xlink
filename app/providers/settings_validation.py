from __future__ import annotations

import base64
import binascii
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

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
            raise ValidationError("REALITY requires a publicKey.", code="profile_settings_invalid")
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


def _wg_key_bytes(settings: dict[str, Any], key: str, label: str) -> bytes:
    _require(settings, key, label)
    raw = str(settings[key]).strip()
    try:
        decoded = base64.standard_b64decode(raw)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError(
            f"{label} is not valid base64.", code="profile_settings_invalid"
        ) from exc
    if len(decoded) != 32:
        raise ValidationError(
            f"{label} must be a 32-byte WireGuard key.", code="profile_settings_invalid"
        )
    return decoded


def _validate_wireguard(protocol: str, settings: dict[str, Any]) -> None:
    _port(settings)
    _require(settings, "address", "Interface address")
    priv = _wg_key_bytes(settings, "privateKey", "Server private key")
    _wg_key_bytes(settings, "publicKey", "Server public key")

    derived = base64.standard_b64encode(
        x25519.X25519PrivateKey.from_private_bytes(priv)
        .public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode("ascii")
    if derived != str(settings["publicKey"]).strip():
        raise ValidationError(
            "Server publicKey does not match privateKey — they must be a "
            "matching WireGuard key pair.",
            code="profile_settings_invalid",
        )
    _wg_mtu(settings)


def _wg_mtu(settings: dict[str, Any]) -> None:
    """Reject an out-of-range MTU at save time.

    All three layers (panel store, node agent, client config) share the
    1280..1500 window. Accepting 9000 here and clamping it downstream meant the
    operator saw a successful save while the tunnel quietly used a different
    value, so this is a hard error rather than a silent correction.
    """
    raw = settings.get("mtu")
    if raw in (None, ""):
        return
    try:
        mtu = int(raw)
    except (TypeError, ValueError):
        raise ValidationError(
            "MTU must be a whole number.", code="profile_settings_invalid"
        ) from None
    if not (1280 <= mtu <= 1500):
        raise ValidationError(
            f"MTU must be between 1280 and 1500 (got {mtu}). 1420 suits most networks.",
            code="profile_settings_invalid",
        )


_VALIDATORS = {
    ProviderKind.SING_BOX: _validate_singbox,
    ProviderKind.HYSTERIA: _validate_hysteria,
    ProviderKind.WIREGUARD: _validate_wireguard,
}


_RAW_FIELDS = {
    # field -> keys it may not touch (mirrors node-agent _RAW_PROTECTED and
    # subscription/formats/raw_override._PROTECTED)
    "rawInbound": frozenset(
        {"tag", "listen", "port", "listen_port", "users", "clients", "type", "protocol"}
    ),
    "rawClientOutbound": frozenset(
        {"tag", "type", "protocol", "server", "server_port", "uuid", "password",
         "users", "vnext", "servers"}
    ),
}
_RAW_MAX_BYTES = 16 * 1024


def _validate_raw_overrides(settings: dict[str, Any]) -> None:
    """Passthrough overrides are validated up front so a bad one fails the save
    instead of being half-applied (or silently dropped) on the node."""
    import json

    for field, protected in _RAW_FIELDS.items():
        raw = settings.get(field)
        if raw in (None, "", {}):
            continue
        if not isinstance(raw, dict):
            raise ValidationError(
                f"{field} must be a JSON object.", code="profile_settings_invalid"
            )
        try:
            size = len(json.dumps(raw))
        except (TypeError, ValueError):
            raise ValidationError(
                f"{field} must be plain JSON.", code="profile_settings_invalid"
            ) from None
        if size > _RAW_MAX_BYTES:
            raise ValidationError(
                f"{field} is too large ({size} bytes, max {_RAW_MAX_BYTES}).",
                code="profile_settings_invalid",
            )
        clash = sorted(set(raw) & protected)
        if clash:
            raise ValidationError(
                f"{field} may not set {', '.join(clash)} — the panel manages those.",
                code="profile_settings_invalid",
            )


def validate_profile_settings(
    kind: ProviderKind, protocol: str, settings: dict[str, Any] | None
) -> None:
    _validate_raw_overrides(settings or {})
    validator = _VALIDATORS.get(kind)
    if validator is None:
        return
    validator(str(protocol or "").strip().lower(), settings or {})
