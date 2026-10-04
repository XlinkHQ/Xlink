from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field

from app.dependencies.auth import SudoAdminUser
from app.schemas.base import APIModel, InputModel
from app.services import reality_scan

router = APIRouter(prefix="/reality", tags=["reality"])


class RealityScanRequest(InputModel):
    targets: list[str] = Field(min_length=1, max_length=reality_scan.MAX_TARGETS)


class RealityScanItem(APIModel):
    target: str
    port: int
    ip: str | None
    ok: bool
    tls13: bool
    h2: bool
    x25519: bool | None
    cert_valid: bool
    latency_ms: float | None
    issuer: str | None
    problems: list[str]


@router.post("/scan", response_model=list[RealityScanItem])
async def scan_targets(payload: RealityScanRequest, _admin: SudoAdminUser) -> list[RealityScanItem]:
    results = await reality_scan.scan(payload.targets)
    return [RealityScanItem.model_validate(r.as_dict()) for r in results]
