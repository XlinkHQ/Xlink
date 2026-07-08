from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProviderCapability(StrEnum):
    CREATE_CLIENT = "create_client"
    UPDATE_CLIENT = "update_client"
    DELETE_CLIENT = "delete_client"
    GET_CLIENT = "get_client"


class ProviderKind(StrEnum):
    XRAY = "xray"
    SING_BOX = "sing-box"
    HYSTERIA = "hysteria"
    WIREGUARD = "wireguard"


# Which client protocols each provider can actually create. Single source of
# truth shared by the profile validator and (mirrored in) the web UI's
# protocolsFor(); keep the two in sync.
PROVIDER_PROTOCOLS: dict[ProviderKind, frozenset[str]] = {
    ProviderKind.XRAY: frozenset(
        {"vless", "vmess", "trojan", "shadowsocks", "shadowsocks2022"}
    ),
    ProviderKind.SING_BOX: frozenset(
        {
            "vless",
            "vmess",
            "trojan",
            "shadowsocks",
            "shadowsocks2022",
            "shadowtls",
            "hysteria2",
            "tuic",
            "naive",
            "socks",
        }
    ),
    ProviderKind.HYSTERIA: frozenset({"hysteria2"}),
    ProviderKind.WIREGUARD: frozenset({"wireguard"}),
}


def protocols_for(kind: ProviderKind) -> frozenset[str]:
    return PROVIDER_PROTOCOLS.get(kind, frozenset())


class ProviderMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    kind: ProviderKind
    version: str = "0.1.0"
    capabilities: frozenset[ProviderCapability] = Field(default_factory=frozenset)

    def supports(self, capability: ProviderCapability) -> bool:
        return capability in self.capabilities


class ClientSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    client_id: str
    email: str | None = None
    inbound_tag: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class ClientResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_id: str
    provider: str
    raw: dict[str, Any] = Field(default_factory=dict)
