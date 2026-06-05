from __future__ import annotations

from abc import ABC, abstractmethod

from app.providers.base.exceptions import CapabilityNotSupportedError
from app.providers.base.models import (
    ClientResult,
    ClientSpec,
    ProviderCapability,
    ProviderMetadata,
)


class Provider(ABC):
    @property
    @abstractmethod
    def metadata(self) -> ProviderMetadata: ...

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def capabilities(self) -> frozenset[ProviderCapability]:
        return self.metadata.capabilities

    def supports(self, capability: ProviderCapability) -> bool:
        return self.metadata.supports(capability)

    def ensure_capability(self, capability: ProviderCapability) -> None:
        if not self.supports(capability):
            raise CapabilityNotSupportedError(
                f"Provider '{self.name}' does not support {capability.value}.",
                details={"provider": self.name, "capability": capability.value},
            )

    @abstractmethod
    async def create_client(self, spec: ClientSpec) -> ClientResult: ...

    @abstractmethod
    async def update_client(self, spec: ClientSpec) -> ClientResult: ...

    @abstractmethod
    async def delete_client(self, client_id: str) -> None: ...

    @abstractmethod
    async def get_client(self, client_id: str) -> ClientResult: ...
