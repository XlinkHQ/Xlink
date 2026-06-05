from __future__ import annotations

from collections.abc import Mapping

from app.provider_sdk.loader import ProviderLoader
from app.provider_sdk.manifest import ProviderManifest
from app.provider_sdk.validator import ProviderManifestValidator
from app.providers.base.provider import Provider
from app.providers.base.registry import ProviderRegistry


class ProviderSDKService:
    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        providers: Mapping[str, Provider],
        platform_version: str = "0.1.0",
    ) -> None:
        self._registry = registry
        self._loader = ProviderLoader(providers)
        self._validator = ProviderManifestValidator(platform_version=platform_version)

    def register_from_manifest(
        self,
        manifest: ProviderManifest,
        *,
        replace: bool = False,
    ) -> Provider:
        provider = self._loader.load(manifest)
        self._validator.validate(manifest, provider)
        return self._registry.register(provider, replace=replace)

    def negotiate(self, manifest: ProviderManifest, provider: Provider) -> frozenset[str]:
        self._validator.validate(manifest, provider)
        return frozenset(capability.value for capability in manifest.capabilities)
