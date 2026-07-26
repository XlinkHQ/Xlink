from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.dependencies.auth import SudoAdminUser
from app.dependencies.core import DatabaseDep
from app.domain.audit_log import AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


def _audit_query(
    *,
    actor: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if actor:
        needle = actor.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(AuditLog.actor_username.ilike(f"%{needle}%", escape="\\"))
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        end = date_to
        if end.hour == 0 and end.minute == 0 and end.second == 0:
            end = end + timedelta(days=1)
        stmt = stmt.where(AuditLog.created_at < end)
    return stmt


class AuditEntry(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_username: str
    method: str
    path: str
    action: str
    status_code: int
    ip_address: str
    created_at: datetime


@router.get("", response_model=list[AuditEntry])
async def list_audit(
    _admin: SudoAdminUser,
    database: DatabaseDep,
    limit: int = Query(default=200, ge=1, le=1000),
    actor: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> list[AuditEntry]:
    async with database.session() as session:
        stmt = _audit_query(actor=actor, date_from=date_from, date_to=date_to, limit=limit)
        rows = (await session.execute(stmt)).scalars().all()
    return [AuditEntry.model_validate(r, from_attributes=True) for r in rows]


def _csv_safe(value: object) -> str:
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


@router.get("/export.csv")
async def export_audit_csv(
    _admin: SudoAdminUser,
    database: DatabaseDep,
    actor: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> StreamingResponse:
    async with database.session() as session:
        stmt = _audit_query(actor=actor, date_from=date_from, date_to=date_to, limit=100000)
        rows = (await session.execute(stmt)).scalars().all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["timestamp", "actor", "action", "method", "path", "status_code", "ip_address"]
    )
    for r in rows:
        writer.writerow(
            [
                r.created_at.isoformat() if r.created_at else "",
                _csv_safe(r.actor_username),
                _csv_safe(r.action),
                _csv_safe(r.method),
                _csv_safe(r.path),
                r.status_code,
                _csv_safe(r.ip_address),
            ]
        )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"content-disposition": "attachment; filename=xlink-audit.csv"},
    )
