from __future__ import annotations

from enum import StrEnum
from typing import Any


class XrayProtocol(StrEnum):
    VLESS = "vless"
    VMESS = "vmess"
    TROJAN = "trojan"
    SHADOWSOCKS = "shadowsocks"
    SHADOWSOCKS2022 = "shadowsocks2022"


class XrayNetwork(StrEnum):
    TCP = "tcp"
    WS = "ws"
    GRPC = "grpc"
    HTTPUPGRADE = "httpupgrade"
    XHTTP = "xhttp"


class XraySecurity(StrEnum):
    NONE = "none"
    TLS = "tls"
    REALITY = "reality"


SUPPORTED_PROTOCOLS: frozenset[str] = frozenset(p.value for p in XrayProtocol)

UUID_PROTOCOLS: frozenset[str] = frozenset({XrayProtocol.VLESS.value, XrayProtocol.VMESS.value})

PASSWORD_PROTOCOLS: frozenset[str] = frozenset(
    {XrayProtocol.SHADOWSOCKS.value, XrayProtocol.SHADOWSOCKS2022.value}
)

SHADOWSOCKS_METHODS: frozenset[str] = frozenset(
    {
        "aes-128-gcm",
        "aes-256-gcm",
        "chacha20-ietf-poly1305",
    }
)
SHADOWSOCKS2022_METHODS: frozenset[str] = frozenset(
    {
        "2022-blake3-aes-128-gcm",
        "2022-blake3-aes-256-gcm",
        "2022-blake3-chacha20-poly1305",
    }
)
DEFAULT_SHADOWSOCKS_METHOD = "aes-256-gcm"
DEFAULT_SHADOWSOCKS2022_METHOD = "2022-blake3-aes-256-gcm"


def methods_for(protocol: str) -> frozenset[str]:
    if protocol == XrayProtocol.SHADOWSOCKS2022.value:
        return SHADOWSOCKS2022_METHODS
    return SHADOWSOCKS_METHODS


def default_method_for(protocol: str) -> str:
    if protocol == XrayProtocol.SHADOWSOCKS2022.value:
        return DEFAULT_SHADOWSOCKS2022_METHOD
    return DEFAULT_SHADOWSOCKS_METHOD

SUPPORTED_NETWORKS: frozenset[str] = frozenset(n.value for n in XrayNetwork)

SUPPORTED_SECURITIES: frozenset[str] = frozenset(s.value for s in XraySecurity)

DEFAULT_NETWORK = XrayNetwork.TCP.value
DEFAULT_SECURITY = XraySecurity.NONE.value

CLIENT_DEFAULTS: dict[str, Any] = {
    "flow": "",
    "level": 0,
    "totalGB": 0,
    "expiryTime": 0,
    "enable": True,
    "limitIp": 0,
    "subId": "",
    "tgId": "",
    "reset": 0,
}

OPERATION_CREATE = "create"
OPERATION_UPDATE = "update"
OPERATION_DELETE = "delete"

PROVIDER_NAME = "xray"
