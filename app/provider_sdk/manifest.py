from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.providers.base.models import ProviderCapability, ProviderKind


class ProviderManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    kind: ProviderKind
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    min_platform_version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+$")
    capabilities: frozenset[ProviderCapability] = Field(default_factory=frozenset)
