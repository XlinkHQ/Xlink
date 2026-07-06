from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.providers.xray.exceptions import (
    InvalidStreamSettingsError,
    UnsupportedNetworkError,
    UnsupportedSecurityError,
)
from app.providers.xray.payloads import (
    DEFAULT_NETWORK,
    DEFAULT_SECURITY,
    SUPPORTED_NETWORKS,
    SUPPORTED_SECURITIES,
    XrayNetwork,
    XraySecurity,
)

REALITY_NETWORKS: frozenset[str] = frozenset({XrayNetwork.TCP.value, XrayNetwork.GRPC.value})


def resolve_network(attrs: Mapping[str, Any]) -> str:
    raw = attrs.get("network", DEFAULT_NETWORK)
    network = str(raw).strip().lower()
    if network not in SUPPORTED_NETWORKS:
        raise UnsupportedNetworkError(
            f"Unsupported Xray network '{network}'.",
            details={"network": network},
        )
    return network


def resolve_security(attrs: Mapping[str, Any]) -> str:
    raw = attrs.get("security", DEFAULT_SECURITY)
    security = str(raw).strip().lower()
    if security not in SUPPORTED_SECURITIES:
        raise UnsupportedSecurityError(
            f"Unsupported Xray security '{security}'.",
            details={"security": security},
        )
    return security


def _network_settings(network: str, attrs: Mapping[str, Any]) -> dict[str, Any]:
    if network == XrayNetwork.WS.value:
        return {
            "wsSettings": {
                "path": str(attrs.get("path", "/")),
                "headers": {"Host": str(attrs.get("host", ""))} if attrs.get("host") else {},
            }
        }
    if network == XrayNetwork.HTTPUPGRADE.value:
        return {
            "httpupgradeSettings": {
                "path": str(attrs.get("path", "/")),
                "host": str(attrs.get("host", "")),
            }
        }
    if network == XrayNetwork.GRPC.value:
        return {
            "grpcSettings": {
                "serviceName": str(attrs.get("serviceName", "")),
                "multiMode": bool(attrs.get("multiMode", False)),
            }
        }
    if network == XrayNetwork.XHTTP.value:
        xhttp: dict[str, Any] = {"path": str(attrs.get("path", "/"))}
        if attrs.get("host"):
            xhttp["host"] = str(attrs.get("host"))
        mode = str(attrs.get("mode", "")).strip().lower()
        if mode in ("auto", "packet-up", "stream-up", "stream-one"):
            xhttp["mode"] = mode
        return {"xhttpSettings": xhttp}
    return {
        "tcpSettings": {
            "header": {"type": str(attrs.get("headerType", "none"))},
        }
    }


def _tls_settings(attrs: Mapping[str, Any]) -> dict[str, Any]:
    server_name = str(attrs.get("sni", attrs.get("host", ""))).strip()
    if not server_name:
        raise InvalidStreamSettingsError(
            "TLS requires a serverName (sni).",
            details={"security": "tls"},
        )
    settings: dict[str, Any] = {
        "serverName": server_name,
        "fingerprint": str(attrs.get("fingerprint", "chrome")),
    }
    alpn = attrs.get("alpn")
    if alpn:
        settings["alpn"] = [part.strip() for part in str(alpn).split(",") if part.strip()]
    if attrs.get("allowInsecure"):
        settings["allowInsecure"] = True
    return {"tlsSettings": settings}


def _reality_settings(network: str, attrs: Mapping[str, Any]) -> dict[str, Any]:
    if network not in REALITY_NETWORKS:
        raise InvalidStreamSettingsError(
            f"REALITY is not supported on network '{network}'.",
            details={"network": network, "security": "reality"},
        )
    public_key = str(attrs.get("publicKey", attrs.get("pbk", ""))).strip()
    server_name = str(attrs.get("sni", "")).strip()
    if not public_key:
        raise InvalidStreamSettingsError(
            "REALITY requires a publicKey.",
            details={"security": "reality"},
        )
    if not server_name:
        raise InvalidStreamSettingsError(
            "REALITY requires a serverName (sni).",
            details={"security": "reality"},
        )
    return {
        "realitySettings": {
            "serverName": server_name,
            "fingerprint": str(attrs.get("fingerprint", "chrome")),
            "publicKey": public_key,
            "shortId": str(attrs.get("shortId", attrs.get("sid", ""))),
            "spiderX": str(attrs.get("spiderX", "")),
        }
    }


def build_stream_settings(attrs: Mapping[str, Any]) -> dict[str, Any]:
    network = resolve_network(attrs)
    security = resolve_security(attrs)
    settings: dict[str, Any] = {"network": network, "security": security}
    settings.update(_network_settings(network, attrs))
    if security == XraySecurity.TLS.value:
        settings.update(_tls_settings(attrs))
    elif security == XraySecurity.REALITY.value:
        settings.update(_reality_settings(network, attrs))
    return settings
