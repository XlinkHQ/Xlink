from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.backup.models import BackupDocument
from app.backup.schemas import BackupRead, RestoreResult
from app.dependencies.auth import AdminUser
from app.dependencies.services import BackupServiceDep

router = APIRouter(prefix="/backup", tags=["backup"])


class BackupExportRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    since: datetime | None = None


class BackupRestoreRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    document: dict[str, Any]
    dry_run: bool = False


def _backup_read(document: BackupDocument) -> BackupRead:
    return BackupRead(
        schema_version=document.schema_version,
        scope=document.scope,
        exported_at=document.exported_at,
        data=document.data,
        checksum=document.checksum,
    )


@router.post("/export", response_model=BackupRead)
async def backup_export(
    payload: BackupExportRequest,
    _admin: AdminUser,
    backup: BackupServiceDep,
) -> BackupRead:
    if payload.since is not None:
        document = await backup.export_incremental(since=payload.since)
    else:
        document = await backup.export_full()
    return _backup_read(document)


@router.post("/restore", response_model=RestoreResult)
async def backup_restore(
    payload: BackupRestoreRequest,
    _admin: AdminUser,
    backup: BackupServiceDep,
) -> RestoreResult:
    return await backup.restore(payload.document, dry_run=payload.dry_run)
