from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.dependencies.auth import AdminUser, SudoAdminUser
from app.dependencies.services import AssignmentServiceDep, GroupServiceDep
from app.schemas.group import GroupCreate, GroupRead, GroupUpdate

router = APIRouter(prefix="/groups", tags=["groups"])


@router.post("", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
async def create_group(
    payload: GroupCreate,
    _admin: SudoAdminUser,
    groups: GroupServiceDep,
) -> GroupRead:
    return GroupRead.model_validate(await groups.create(payload))


@router.get("", response_model=list[GroupRead])
async def list_groups(_admin: AdminUser, groups: GroupServiceDep) -> list[GroupRead]:
    return [GroupRead.model_validate(g) for g in await groups.list_all()]


@router.get("/{group_id}", response_model=GroupRead)
async def get_group(group_id: uuid.UUID, _admin: AdminUser, groups: GroupServiceDep) -> GroupRead:
    return GroupRead.model_validate(await groups.get(group_id))


@router.patch("/{group_id}", response_model=GroupRead)
async def update_group(
    group_id: uuid.UUID,
    payload: GroupUpdate,
    _admin: SudoAdminUser,
    groups: GroupServiceDep,
    assignments: AssignmentServiceDep,
) -> GroupRead:
    group = await groups.update(group_id, payload)
    result = GroupRead.model_validate(group)

    await assignments.sync_group(result.id, [uuid.UUID(str(p)) for p in result.profile_ids])
    return result


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: uuid.UUID, _admin: SudoAdminUser, groups: GroupServiceDep) -> None:
    await groups.delete(group_id)
