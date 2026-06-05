from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.dependencies.auth import AdminUser
from app.dependencies.core import ProvidersDep

router = APIRouter(prefix="/providers", tags=["providers"])


class ProviderRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    kind: str
    version: str
    capabilities: list[str]


@router.get("", response_model=list[ProviderRead])
async def list_providers(
    _admin: AdminUser,
    providers: ProvidersDep,
) -> list[ProviderRead]:
    return [
        ProviderRead(
            name=meta.name,
            kind=str(meta.kind.value if hasattr(meta.kind, "value") else meta.kind),
            version=meta.version,
            capabilities=sorted(
                str(c.value if hasattr(c, "value") else c) for c in meta.capabilities
            ),
        )
        for meta in providers.metadata()
    ]
