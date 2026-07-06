from __future__ import annotations

from app.providers.base.models import (
    ClientResult,
    ClientSpec,
    ProviderCapability,
    ProviderKind,
    ProviderMetadata,
)
from app.providers.base.provider import Provider
from app.providers.xray.client import InMemoryTransport, XrayTransport
from app.providers.xray.config import XrayGatewayConfig
from app.providers.xray.gateway import XrayGateway
from app.providers.xray.mapper import PROVIDER_NAME

_XRAY_CAPABILITIES = frozenset(
    {
        ProviderCapability.CREATE_CLIENT,
        ProviderCapability.UPDATE_CLIENT,
        ProviderCapability.DELETE_CLIENT,
        ProviderCapability.GET_CLIENT,
    }
)
_DEFAULT_PROTOCOL = "trojan"


class XrayProvider(Provider):
    def __init__(
        self,
        gateway: XrayGateway | None = None,
        transport: XrayTransport | None = None,
        config: XrayGatewayConfig | None = None,
    ) -> None:
        if gateway is None:
            gateway = XrayGateway(transport or InMemoryTransport(), config)
        self._gateway = gateway

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name=PROVIDER_NAME,
            kind=ProviderKind.XRAY,
            capabilities=_XRAY_CAPABILITIES,
        )

    async def create_client(self, spec: ClientSpec) -> ClientResult:
        self.ensure_capability(ProviderCapability.CREATE_CLIENT)
        return await self._gateway.create_client(self._with_default_protocol(spec))

    async def update_client(self, spec: ClientSpec) -> ClientResult:
        self.ensure_capability(ProviderCapability.UPDATE_CLIENT)
        return await self._gateway.update_client(self._with_default_protocol(spec))

    async def delete_client(self, client_id: str) -> None:
        self.ensure_capability(ProviderCapability.DELETE_CLIENT)
        await self._gateway.delete_client(client_id)

    async def get_client(self, client_id: str) -> ClientResult:
        self.ensure_capability(ProviderCapability.GET_CLIENT)
        return await self._gateway.get_client(client_id)

    async def health_check(self) -> bool:
        return await self._gateway.health_check()

    def _with_default_protocol(self, spec: ClientSpec) -> ClientSpec:
        if "protocol" in spec.attributes:
            return spec
        return spec.model_copy(
            update={"attributes": {**spec.attributes, "protocol": _DEFAULT_PROTOCOL}}
        )
