from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.dependencies.auth import AdminUser
from app.dependencies.pagination import CursorPaginationDep
from app.dependencies.services import ProfileServiceDep
from app.providers.base.models import ProviderKind
from app.schemas.pagination import CursorPage
from app.schemas.profile import ProfileCreate, ProfileRead, ProfileUpdate

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.post("", response_model=ProfileRead, status_code=status.HTTP_201_CREATED)
async def create_profile(
    payload: ProfileCreate,
    _admin: AdminUser,
    profiles: ProfileServiceDep,
) -> ProfileRead:
    profile = await profiles.create(payload)
    return ProfileRead.model_validate(profile)


@router.get("", response_model=CursorPage[ProfileRead])
async def list_profiles(
    _admin: AdminUser,
    pagination: CursorPaginationDep,
    profiles: ProfileServiceDep,
    provider_kind: ProviderKind | None = None,
    node_id: uuid.UUID | None = None,
    is_active: bool | None = None,
) -> CursorPage[ProfileRead]:
    rows, next_cursor = await profiles.list_profiles_keyset(
        pagination,
        provider_kind=provider_kind,
        node_id=node_id,
        is_active=is_active,
    )
    items = [ProfileRead.model_validate(p) for p in rows]
    return CursorPage(items=items, next_cursor=next_cursor, size=pagination.size)


@router.get("/{profile_id}", response_model=ProfileRead)
async def get_profile(
    profile_id: uuid.UUID,
    _admin: AdminUser,
    profiles: ProfileServiceDep,
) -> ProfileRead:
    profile = await profiles.get(profile_id)
    return ProfileRead.model_validate(profile)


@router.patch("/{profile_id}", response_model=ProfileRead)
async def update_profile(
    profile_id: uuid.UUID,
    payload: ProfileUpdate,
    _admin: AdminUser,
    profiles: ProfileServiceDep,
) -> ProfileRead:
    profile = await profiles.update(profile_id, payload)
    return ProfileRead.model_validate(profile)


@router.post("/{profile_id}/disable", response_model=ProfileRead)
async def disable_profile(
    profile_id: uuid.UUID,
    _admin: AdminUser,
    profiles: ProfileServiceDep,
) -> ProfileRead:
    profile = await profiles.disable(profile_id)
    return ProfileRead.model_validate(profile)
