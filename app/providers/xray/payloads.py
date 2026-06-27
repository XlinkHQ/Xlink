from __future__ import annotations

from enum import StrEnum
from typing import Any


class XrayProtocol(StrEnum):
    VLESS = "vless"
    VMESS = "vmess"
    TROJAN = "trojan"


class XrayNetwork(StrEnum):
    TCP = "tcp"
    WS = "ws"
    GRPC = "grpc"
    HTTPUPGRADE = "httpupgrade"


class XraySecurity(StrEnum):
    NONE = "none"
    TLS = "tls"
    REALITY = "reality"


SUPPORTED_PROTOCOLS: frozenset[str] = frozenset(p.value for p in XrayProtocol)

UUID_PROTOCOLS: frozenset[str] = frozenset({XrayProtocol.VLESS.value, XrayProtocol.VMESS.value})

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
