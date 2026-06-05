from __future__ import annotations

from collections.abc import Mapping

from app.core.exceptions import NotFoundError
from app.provider_sdk.manifest import ProviderManifest
from app.providers.base.provider import Provider


class ProviderLoader:
    def __init__(self, providers: Mapping[str, Provider]) -> None:
        self._providers = dict(providers)

    def load(self, manifest: ProviderManifest) -> Provider:
        try:
            return self._providers[manifest.name]
        except KeyError as exc:
            raise NotFoundError(
                "Provider implementation is not available.",
                code="provider_implementation_not_found",
                details={"provider": manifest.name},
            ) from exc
