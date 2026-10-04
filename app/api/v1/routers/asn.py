from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.dependencies.auth import SudoAdminUser
from app.dependencies.core import SettingsDep
from app.services.asn_lookup import get_db

router = APIRouter(prefix="/asn", tags=["asn"])


@router.get("/status")
async def asn_status(_admin: SudoAdminUser, settings: SettingsDep) -> dict[str, Any]:
    """Loaded IP→ASN ranges per family; empty until /asn/refresh has run."""
    return await get_db(settings.asn_data_dir).status()


@router.post("/refresh")
async def asn_refresh(_admin: SudoAdminUser, settings: SettingsDep) -> dict[str, Any]:
    """Download the current iptoasn.com dataset (fixed URLs, ~10 MB)."""
    try:
        return await get_db(settings.asn_data_dir).download()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"ASN download failed: {exc}") from exc


@router.get("/lookup")
async def asn_lookup(
    _admin: SudoAdminUser,
    settings: SettingsDep,
    ip: str = Query(min_length=2, max_length=64),
) -> dict[str, Any]:
    """Which ASN an address belongs to — to check a mapping before relying on it."""
    return {"ip": ip, "asn": await get_db(settings.asn_data_dir).lookup(ip)}
