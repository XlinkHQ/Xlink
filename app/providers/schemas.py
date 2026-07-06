from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ProviderRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    kind: str
    version: str
    capabilities: list[str]
