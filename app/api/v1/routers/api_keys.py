from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from app.core.security import hash_token
from app.dependencies.auth import AdminUser
from app.dependencies.core import DatabaseDep
from app.domain.api_key import ApiKey

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class ApiKeyRead(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreate(BaseModel):
    name: str = ""


class ApiKeyCreated(ApiKeyRead):
    token: str


class ApiKeyPage(BaseModel):
    items: list[ApiKeyRead]
    total: int
    next_offset: int | None


@router.get("", response_model=ApiKeyPage)
async def list_api_keys(
    admin: AdminUser,
    database: DatabaseDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ApiKeyPage:
    async with database.session() as session:
        total = int(
            await session.scalar(
                select(func.count()).select_from(ApiKey).where(ApiKey.user_id == admin.id)
            )
            or 0
        )
        rows = (
            (
                await session.execute(
                    select(ApiKey)
                    .where(ApiKey.user_id == admin.id)
                    .order_by(ApiKey.created_at.desc(), ApiKey.prefix.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
    next_offset = offset + limit if offset + limit < total else None
    return ApiKeyPage(
        items=[ApiKeyRead.model_validate(r, from_attributes=True) for r in rows],
        total=total,
        next_offset=next_offset,
    )


@router.post("", response_model=ApiKeyCreated)
async def create_api_key(
    payload: ApiKeyCreate, admin: AdminUser, database: DatabaseDep
) -> ApiKeyCreated:
    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    token = f"xlk_{prefix}_{secret}"
    row = ApiKey(
        user_id=admin.id,
        name=payload.name.strip()[:128],
        prefix=prefix,
        token_hash=hash_token(token),
    )
    async with database.session() as session:
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return ApiKeyCreated(
            id=row.id,
            name=row.name,
            prefix=row.prefix,
            last_used_at=row.last_used_at,
            revoked_at=row.revoked_at,
            created_at=row.created_at,
            token=token,
        )


async def _owned_key(session, key_id: uuid.UUID, admin: AdminUser) -> ApiKey:
    row = (
        await session.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == admin.id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="API key not found.")
    return row


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(key_id: uuid.UUID, admin: AdminUser, database: DatabaseDep) -> None:
    async with database.session() as session:
        row = await _owned_key(session, key_id, admin)
        if row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)


@router.post("/{key_id}/enable", response_model=ApiKeyRead)
async def enable_api_key(key_id: uuid.UUID, admin: AdminUser, database: DatabaseDep) -> ApiKeyRead:
    async with database.session() as session:
        row = await _owned_key(session, key_id, admin)
        row.revoked_at = None
        await session.flush()
        await session.refresh(row)
        return ApiKeyRead.model_validate(row, from_attributes=True)


@router.delete("/{key_id}/purge", status_code=204)
async def purge_api_key(key_id: uuid.UUID, admin: AdminUser, database: DatabaseDep) -> None:
    async with database.session() as session:
        await _owned_key(session, key_id, admin)
        await session.execute(delete(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == admin.id))
