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




def protocols_for(kind: ProviderKind) -> frozenset[str]:
    from app.protocols import protocols_for as _protocols_for

    return _protocols_for(kind)


def __getattr__(name: str) -> Any:
    if name == "PROVIDER_PROTOCOLS":
        from app.protocols import provider_protocols

        return provider_protocols()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
