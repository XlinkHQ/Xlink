from __future__ import annotations

from collections.abc import Iterable

from app.providers.base.exceptions import (
    ProviderAlreadyRegisteredError,
    ProviderNotFoundError,
)
from app.providers.base.models import ProviderCapability, ProviderKind, ProviderMetadata
from app.providers.base.provider import Provider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider, *, replace: bool = False) -> Provider:
        name = provider.name
        if name in self._providers and not replace:
            raise ProviderAlreadyRegisteredError(
                f"Provider '{name}' is already registered.",
                details={"provider": name},
            )
        self._providers[name] = provider
        return provider

    def unregister(self, name: str) -> None:
        if name not in self._providers:
            raise ProviderNotFoundError(
                f"Provider '{name}' is not registered.", details={"provider": name}
            )
        del self._providers[name]

    def get(self, name: str) -> Provider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ProviderNotFoundError(
                f"Provider '{name}' is not registered.", details={"provider": name}
            ) from exc

    def get_by_kind(self, kind: ProviderKind) -> Provider:
        for provider in self._providers.values():
            if provider.metadata.kind is kind:
                return provider
        raise ProviderNotFoundError(
            f"No provider registered for kind '{kind.value}'.",
            details={"kind": kind.value},
        )

    def has(self, name: str) -> bool:
        return name in self._providers

    def names(self) -> list[str]:
        return sorted(self._providers)

    def all(self) -> list[Provider]:
        return list(self._providers.values())

    def metadata(self) -> list[ProviderMetadata]:
        return [provider.metadata for provider in self._providers.values()]

    def with_capability(self, capability: ProviderCapability) -> list[Provider]:
        return [p for p in self._providers.values() if p.supports(capability)]

    def discover(self, providers: Iterable[Provider], *, replace: bool = False) -> None:
        for provider in providers:
            self.register(provider, replace=replace)

    def __len__(self) -> int:
        return len(self._providers)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._providers
