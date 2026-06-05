from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.dependencies.auth import AdminUser, CurrentUser
from app.dependencies.pagination import CursorPaginationDep, ListPaginationDep
from app.dependencies.services import UserServiceDep
from app.domain.user import UserRole
from app.schemas.pagination import CursorPage, CursorParams, Page, PaginationParams
from app.schemas.user import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


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
    _admin: AdminUser,
    pagination: ListPaginationDep,
    users: UserServiceDep,
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> CursorPage[UserRead] | Page[UserRead]:
    if isinstance(pagination, PaginationParams):
        rows, total = await users.list_users(pagination, role=role, is_active=is_active)
        items = [UserRead.model_validate(u) for u in rows]
        return Page.create(items, total, pagination)

    keyset: CursorParams = pagination
    rows, next_cursor = await users.list_users_keyset(keyset, role=role, is_active=is_active)
    items = [UserRead.model_validate(u) for u in rows]
    return CursorPage(items=items, next_cursor=next_cursor, size=keyset.size)


@router.get("/cursor", response_model=CursorPage[UserRead])
async def list_users_cursor(
    _admin: AdminUser,
    pagination: CursorPaginationDep,
    users: UserServiceDep,
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> CursorPage[UserRead]:
    rows, next_cursor = await users.list_users_keyset(pagination, role=role, is_active=is_active)
    items = [UserRead.model_validate(u) for u in rows]
    return CursorPage(items=items, next_cursor=next_cursor, size=pagination.size)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    _admin: AdminUser,
    users: UserServiceDep,
) -> UserRead:
    user = await users.get(user_id)
    return UserRead.model_validate(user)
