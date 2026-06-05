from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.provider_sdk.manifest import ProviderManifest


class ProviderInstallRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    manifest: ProviderManifest
    replace: bool = False


class ProviderInstallResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    capabilities: frozenset[str]
