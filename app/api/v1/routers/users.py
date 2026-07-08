from __future__ import annotations

import csv
import io
import uuid
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.authz import owner_scope
from app.core.exceptions import ValidationError
from app.dependencies.auth import AdminUser, CurrentUser, SudoAdminUser, WriteAdminUser
from app.dependencies.core import DatabaseDep
from app.dependencies.pagination import ListPaginationDep
from app.dependencies.services import (
    AssignmentServiceDep,
    ProfileServiceDep,
    UserServiceDep,
)
from app.domain.user import User, UserRole
from app.repositories.user import UserRepository
from app.schemas.pagination import CursorPage, CursorParams, Page, PaginationParams
from app.schemas.client_assignment import AssignmentCreate
from app.schemas.user import AdminUpdate, UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


class UserDeviceRead(BaseModel):
    id: uuid.UUID
    device_hash: str
    user_agent: str
    first_seen_at: datetime
    last_seen_at: datetime


def _guard_not_self(admin: User, user_id: uuid.UUID) -> None:
    if admin.id == user_id:
        raise ValidationError(
            "You cannot perform this action on your own account.",
            code="self_action_forbidden",
        )


async def _scoped_get(users, admin: User, user_id: uuid.UUID) -> User:
    user = await users.get(user_id)
    users.assert_can_manage(admin, user)
    return user


def _owner_filter(admin: User) -> uuid.UUID | None:
    return owner_scope(admin)


@router.get("/me", response_model=UserRead)
async def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("/me", response_model=UserRead)
async def update_me(
    payload: UserUpdate,
    user: CurrentUser,
    users: UserServiceDep,
) -> UserRead:
    updated = await users.update_profile(user.id, payload)
    return UserRead.model_validate(updated)


@router.get("", response_model=CursorPage[UserRead] | Page[UserRead])
async def list_users(
    admin: AdminUser,
    pagination: ListPaginationDep,
    users: UserServiceDep,
    role: UserRole | None = None,
    is_active: bool | None = None,
    include_removed: bool = False,
    search: str | None = None,
    sort: str | None = None,
) -> CursorPage[UserRead] | Page[UserRead]:

    owner_id = _owner_filter(admin)
    if isinstance(pagination, PaginationParams):
        rows, total = await users.list_users(
            pagination,
            role=role,
            is_active=is_active,
            include_removed=include_removed,
            owner_id=owner_id,
            search=search,
            sort=sort,
        )
        items = [UserRead.model_validate(u) for u in rows]
        return Page.create(items, total, pagination)

    keyset: CursorParams = pagination
    rows, next_cursor = await users.list_users_keyset(
        keyset,
        role=role,
        is_active=is_active,
        include_removed=include_removed,
        owner_id=owner_id,
        search=search,
        sort=sort,
    )
    items = [UserRead.model_validate(u) for u in rows]
    return CursorPage(items=items, next_cursor=next_cursor, size=keyset.size)


@router.get("/export.csv")
async def export_users_csv(
    admin: AdminUser,
    database: DatabaseDep,
) -> StreamingResponse:
    owner_id = _owner_filter(admin)

    # Open a SHORT session per batch inside the generator rather than depending on
    # a request-scoped session: the response body streams for the whole download,
    # and a request-scoped DB connection would stay checked out that entire time
    # (slow clients pin pool connections → QueuePool exhaustion). Batches are
    # independent reads, so per-batch sessions are fine for a CSV export.
    async def rows() -> AsyncIterator[str]:
        header = io.StringIO()
        writer = csv.writer(header)
        writer.writerow(
            ["username", "email", "status", "on_hold", "data_limit_bytes", "expire_at", "created_at"]
        )
        yield header.getvalue()
        offset = 0
        while True:
            async with database.session() as session:
                batch, total = await UserRepository(session).list_paginated(
                    offset=offset,
                    limit=500,
                    role=UserRole.USER,
                    is_active=None,
                    include_removed=False,
                    owner_id=owner_id,
                )
            for u in batch:
                status_label = (
                    "disabled" if not u.is_active else "on_hold" if u.on_hold else "active"
                )
                line = io.StringIO()
                csv.writer(line).writerow(
                    [
                        u.username,
                        u.email or "",
                        status_label,
                        "yes" if u.on_hold else "no",
                        u.data_limit_bytes if u.data_limit_bytes is not None else "",
                        u.expire_at.isoformat() if u.expire_at else "",
                        u.created_at.isoformat() if u.created_at else "",
                    ]
                )
                yield line.getvalue()
            offset += len(batch)
            if not batch or offset >= total:
                break

    return StreamingResponse(
        rows(),
        media_type="text/csv",
        headers={"content-disposition": "attachment; filename=xlink-users.csv"},
    )


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    admin: WriteAdminUser,
    users: UserServiceDep,
    profiles: ProfileServiceDep,
    assignments: AssignmentServiceDep,
) -> UserRead:
    owner_id = None if admin.is_sudo else admin.id
    user = await users.create(payload, owner_id=owner_id)
    # Optional one-call provisioning: assign the new user to the given profiles so
    # a raw API client (bot) gets user + working config without a second request.
    for profile_id in payload.profile_ids or []:
        profile = await profiles.get(profile_id)
        await assignments.create(
            AssignmentCreate(
                user_id=user.id,
                profile_id=profile.id,
                node_id=profile.node_id,
                provider_kind=profile.provider_kind,
            )
        )
    return UserRead.model_validate(user)


class BulkUserAction(BaseModel):
    action: str
    user_ids: list[uuid.UUID]
    data_limit_bytes: int | None = None
    expire_at: datetime | None = None
    extend_days: int | None = None
    data_reset_strategy: str | None = None


_BULK_ACTIONS = {
    "enable",
    "disable",
    "delete",
    "reset_usage",
    "set_data_limit",
    "set_expiry",
    "extend_expiry",
    "set_reset_strategy",
}


@router.post("/bulk")
async def bulk_user_action(
    payload: BulkUserAction,
    admin: WriteAdminUser,
    users: UserServiceDep,
) -> dict[str, int]:
    if payload.action not in _BULK_ACTIONS:
        raise ValidationError("Unknown bulk action.", code="unknown_bulk_action")
    if len(payload.user_ids) > 1000:
        raise ValidationError("Too many users in one request (max 1000).", code="bulk_too_large")
    return await users.bulk_action(
        payload.action,
        payload.user_ids,
        admin=admin,
        data_limit_bytes=payload.data_limit_bytes,
        expire_at=payload.expire_at,
        extend_days=payload.extend_days,
        data_reset_strategy=payload.data_reset_strategy,
    )


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    admin: AdminUser,
    users: UserServiceDep,
) -> UserRead:
    return UserRead.model_validate(await _scoped_get(users, admin, user_id))


@router.get("/{user_id}/devices", response_model=list[UserDeviceRead])
async def list_user_devices(
    user_id: uuid.UUID,
    admin: AdminUser,
    users: UserServiceDep,
) -> list[UserDeviceRead]:
    await _scoped_get(users, admin, user_id)
    devices = await users.list_devices(user_id)
    return [UserDeviceRead.model_validate(d, from_attributes=True) for d in devices]


@router.delete("/{user_id}/devices", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_devices(
    user_id: uuid.UUID,
    admin: AdminUser,
    users: UserServiceDep,
) -> None:
    await _scoped_get(users, admin, user_id)
    await users.reset_devices(user_id)


@router.post("/{user_id}/disable", response_model=UserRead)
async def disable_user(
    user_id: uuid.UUID,
    admin: WriteAdminUser,
    users: UserServiceDep,
) -> UserRead:
    _guard_not_self(admin, user_id)
    await _scoped_get(users, admin, user_id)
    user = await users.disable(user_id)
    return UserRead.model_validate(user)


@router.post("/{user_id}/enable", response_model=UserRead)
async def enable_user(
    user_id: uuid.UUID,
    admin: WriteAdminUser,
    users: UserServiceDep,
) -> UserRead:
    _guard_not_self(admin, user_id)
    await _scoped_get(users, admin, user_id)
    user = await users.enable(user_id)
    return UserRead.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    admin: WriteAdminUser,
    users: UserServiceDep,
    purge: bool = False,
) -> None:
    _guard_not_self(admin, user_id)
    await _scoped_get(users, admin, user_id)
    if purge:
        await users.purge(user_id)
    else:
        await users.delete(user_id)


@router.post("/{user_id}/restore", response_model=UserRead)
async def restore_user(
    user_id: uuid.UUID,
    admin: WriteAdminUser,
    users: UserServiceDep,
) -> UserRead:
    await _scoped_get(users, admin, user_id)
    return UserRead.model_validate(await users.restore(user_id))


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    admin: WriteAdminUser,
    users: UserServiceDep,
) -> UserRead:
    await _scoped_get(users, admin, user_id)
    return UserRead.model_validate(await users.update_quota(user_id, payload))


@router.post("/admins", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_admin(
    payload: UserCreate,
    _admin: SudoAdminUser,
    users: UserServiceDep,
) -> UserRead:
    user = await users.create_admin(payload)
    return UserRead.model_validate(user)


@router.patch("/admins/{user_id}", response_model=UserRead)
async def update_admin(
    user_id: uuid.UUID,
    payload: AdminUpdate,
    _admin: SudoAdminUser,
    users: UserServiceDep,
) -> UserRead:
    return UserRead.model_validate(await users.update_admin(user_id, payload))


class AdminUsageRead(BaseModel):
    users_count: int
    users_limit: int | None
    traffic_allocated_bytes: int
    traffic_used_bytes: int
    traffic_budget_bytes: int | None


@router.get("/admins/{user_id}/usage", response_model=AdminUsageRead)
async def admin_usage(
    user_id: uuid.UUID,
    _admin: SudoAdminUser,
    users: UserServiceDep,
) -> AdminUsageRead:
    return AdminUsageRead(**await users.admin_usage(user_id))


@router.post("/admins/{user_id}/enable-users")
async def enable_admin_users(
    user_id: uuid.UUID,
    _admin: SudoAdminUser,
    users: UserServiceDep,
) -> dict[str, int]:
    return {"affected": await users.set_owned_users_active(user_id, active=True)}


@router.post("/admins/{user_id}/disable-users")
async def disable_admin_users(
    user_id: uuid.UUID,
    _admin: SudoAdminUser,
    users: UserServiceDep,
) -> dict[str, int]:
    return {"affected": await users.set_owned_users_active(user_id, active=False)}


@router.post("/{user_id}/revoke-subscription", response_model=UserRead)
async def revoke_subscription(
    user_id: uuid.UUID,
    admin: WriteAdminUser,
    users: UserServiceDep,
) -> UserRead:
    await _scoped_get(users, admin, user_id)
    return UserRead.model_validate(await users.revoke_subscription(user_id))


@router.post("/{user_id}/promote", response_model=UserRead)
async def promote_user(
    user_id: uuid.UUID,
    _admin: SudoAdminUser,
    users: UserServiceDep,
) -> UserRead:
    return UserRead.model_validate(await users.set_role(user_id, UserRole.ADMIN))


@router.post("/{user_id}/demote", response_model=UserRead)
async def demote_user(
    user_id: uuid.UUID,
    admin: SudoAdminUser,
    users: UserServiceDep,
) -> UserRead:
    _guard_not_self(admin, user_id)
    return UserRead.model_validate(await users.set_role(user_id, UserRole.USER))
