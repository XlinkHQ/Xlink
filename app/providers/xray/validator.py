from __future__ import annotations

import uuid
from typing import Any

from app.providers.base.models import ClientSpec
from app.providers.xray.exceptions import (
    InvalidClientIdError,
    InvalidStreamSettingsError,
    MissingEmailError,
    MissingProtocolError,
    UnsupportedNetworkError,
    UnsupportedProtocolError,
    UnsupportedSecurityError,
    XrayPayloadError,
)
from app.providers.xray.payloads import (
    CLIENT_DEFAULTS,
    SUPPORTED_NETWORKS,
    SUPPORTED_PROTOCOLS,
    SUPPORTED_SECURITIES,
    UUID_PROTOCOLS,
    XrayProtocol,
    XraySecurity,
)


def resolve_protocol(spec: ClientSpec) -> str:
    protocol = spec.attributes.get("protocol")
    if protocol is None or not isinstance(protocol, str) or not protocol.strip():
        raise MissingProtocolError()
    protocol = protocol.strip().lower()
    if protocol not in SUPPORTED_PROTOCOLS:
        raise UnsupportedProtocolError(
            f"Unsupported Xray protocol '{protocol}'.",
            details={"protocol": protocol},
        )
    return protocol


def _require_email(email: str | None) -> str:
    if email is None or not isinstance(email, str) or not email.strip():
        raise MissingEmailError()
    return email.strip()


def _require_uuid(client_id: str) -> str:
    try:
        return str(uuid.UUID(client_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise InvalidClientIdError(
            f"Client id '{client_id}' is not a valid UUID.",
            details={"client_id": client_id},
        ) from exc


def _compatible(value: Any, default: Any) -> bool:
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, int):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(default, str):
        return isinstance(value, str)
    return False


def validate_spec(spec: ClientSpec) -> str:
    protocol = resolve_protocol(spec)
    _require_email(spec.email)
    if protocol in UUID_PROTOCOLS:
        _require_uuid(spec.client_id)
    elif not spec.client_id or not str(spec.client_id).strip():
        raise InvalidClientIdError("Client id is required.", details={"client_id": spec.client_id})
    return protocol


def validate_xray_client_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise XrayPayloadError("Payload must be a dict.")
    protocol = payload.get("protocol")
    if not isinstance(protocol, str) or protocol not in SUPPORTED_PROTOCOLS:
        raise UnsupportedProtocolError(
            "Payload protocol is missing or unsupported.",
            details={"protocol": protocol},
        )
    client = payload.get("client")
    if not isinstance(client, dict):
        raise XrayPayloadError("Payload 'client' must be a dict.")
    client_id = client.get("id")
    if not isinstance(client_id, str) or not client_id.strip():
        raise XrayPayloadError("Client 'id' is required.")
    if protocol in UUID_PROTOCOLS:
        _require_uuid(client_id)
    email = client.get("email")
    if not isinstance(email, str) or not email.strip():
        raise MissingEmailError()
    for field, default in CLIENT_DEFAULTS.items():
        if field not in client:
            raise XrayPayloadError(f"Client field '{field}' is missing.")
        if not _compatible(client[field], default):
            raise XrayPayloadError(f"Client field '{field}' has an invalid type.")
    stream = payload.get("streamSettings")
    if stream is not None:
        validate_stream_settings(stream, protocol)
    return payload


def validate_stream_settings(stream: dict, protocol: str) -> dict:
    if not isinstance(stream, dict):
        raise InvalidStreamSettingsError("streamSettings must be a dict.")
    network = stream.get("network")
    if not isinstance(network, str) or network not in SUPPORTED_NETWORKS:
        raise UnsupportedNetworkError(
            "streamSettings network is missing or unsupported.",
            details={"network": network},
        )
    security = stream.get("security")
    if not isinstance(security, str) or security not in SUPPORTED_SECURITIES:
        raise UnsupportedSecurityError(
            "streamSettings security is missing or unsupported.",
            details={"security": security},
        )
    if security == XraySecurity.REALITY.value:
        if protocol != XrayProtocol.VLESS.value:
            raise InvalidStreamSettingsError(
                "REALITY security requires the VLESS protocol.",
                details={"protocol": protocol, "security": security},
            )
        reality = stream.get("realitySettings")
        if not isinstance(reality, dict) or not reality.get("publicKey"):
            raise InvalidStreamSettingsError(
                "REALITY requires realitySettings.publicKey.",
                details={"security": security},
            )
    if security == XraySecurity.TLS.value:
        tls = stream.get("tlsSettings")
        if not isinstance(tls, dict) or not tls.get("serverName"):
            raise InvalidStreamSettingsError(
                "TLS requires tlsSettings.serverName.",
                details={"security": security},
            )
    return stream
