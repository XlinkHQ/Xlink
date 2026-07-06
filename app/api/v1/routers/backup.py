from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import UTC, datetime
from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from app.backup.models import BackupDocument
from app.backup.schemas import BackupExportRequest, BackupRead, BackupRestoreRequest, RestoreResult
from app.dependencies.auth import SudoAdminUser
from app.dependencies.core import SettingsDep
from app.dependencies.services import BackupServiceDep

router = APIRouter(prefix="/backup", tags=["backup"])


async def _communicate(
    proc: asyncio.subprocess.Process, data: bytes | None = None
) -> tuple[bytes, bytes]:
    try:
        return await proc.communicate(input=data)
    except BaseException:
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
        raise


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
    _admin: SudoAdminUser,
    backup: BackupServiceDep,
) -> BackupRead:
    if payload.since is not None:
        document = await backup.export_incremental(since=payload.since)
    else:
        document = await backup.export_full()
    return _backup_read(document)


@router.get("/export-db")
async def backup_export_db(_admin: SudoAdminUser, settings: SettingsDep) -> Response:
    url = settings.database_url
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    if url.startswith("sqlite"):
        path = url.split("///", 1)[-1]
        if not path or not await anyio.to_thread.run_sync(os.path.exists, path):
            raise HTTPException(status_code=404, detail="SQLite database file not found.")
        return FileResponse(
            path,
            media_type="application/x-sqlite3",
            filename=f"xlink-db-{stamp}.db",
        )

    env = {**os.environ, "PGPASSWORD": settings.postgres_password.get_secret_value()}
    proc = await asyncio.create_subprocess_exec(
        "pg_dump",
        "-h",
        settings.postgres_host,
        "-p",
        str(settings.postgres_port),
        "-U",
        settings.postgres_user,
        "-d",
        settings.postgres_db,
        "--no-owner",
        "--no-privileges",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    out, err = await _communicate(proc)
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"pg_dump failed: {err.decode()[:300]}")
    return Response(
        content=out,
        media_type="application/sql",
        headers={"content-disposition": f'attachment; filename="xlink-db-{stamp}.sql"'},
    )


@router.post("/import-db", status_code=204)
async def backup_import_db(
    _admin: SudoAdminUser,
    settings: SettingsDep,
    file: UploadFile,
) -> Response:
    url = settings.database_url
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")

    if url.startswith("sqlite"):
        path = url.split("///", 1)[-1]
        if not path:
            raise HTTPException(status_code=400, detail="Cannot resolve SQLite path.")

        await anyio.to_thread.run_sync(Path(path).write_bytes, data)
        return Response(status_code=204)

    env = {**os.environ, "PGPASSWORD": settings.postgres_password.get_secret_value()}
    proc = await asyncio.create_subprocess_exec(
        "psql",
        "-h",
        settings.postgres_host,
        "-p",
        str(settings.postgres_port),
        "-U",
        settings.postgres_user,
        "-d",
        settings.postgres_db,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    _, err = await _communicate(proc, data)
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"psql restore failed: {err.decode()[:300]}")
    return Response(status_code=204)


@router.post("/restore", response_model=RestoreResult)
async def backup_restore(
    payload: BackupRestoreRequest,
    _admin: SudoAdminUser,
    backup: BackupServiceDep,
) -> RestoreResult:
    return await backup.restore(payload.document, dry_run=payload.dry_run)
