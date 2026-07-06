from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.core.authz import assert_group_in_scope, owner_scope
from app.core.exceptions import PermissionDeniedError
from app.dependencies.auth import AdminUser, WriteAdminUser
from app.dependencies.pagination import CursorPaginationDep
from app.dependencies.services import AssignmentServiceDep, UserServiceDep
from app.domain.client_assignment import AssignmentStatus
from app.providers.base.models import ProviderKind
from app.schemas.client_assignment import (
    AssignmentCreate,
    AssignmentRead,
    AssignmentUpdate,
)
from app.schemas.pagination import CursorPage

router = APIRouter(prefix="/assignments", tags=["assignments"])


@router.post("", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    payload: AssignmentCreate,
    admin: WriteAdminUser,
    assignments: AssignmentServiceDep,
    users: UserServiceDep,
) -> AssignmentRead:
    users.assert_can_manage(admin, await users.get(payload.user_id))
    if not admin.is_sudo and not admin.all_groups_access:
        scoped = await users.scoped_group_ids(admin.id)
        assert_group_in_scope(admin, payload.group_id, scoped)
        # Also ensure the target profile is one the reseller may actually use,
        # so they can't pin an owned user onto an out-of-scope profile/node.
        scoped_profiles = await users.scoped_profile_ids(admin.id)
        if payload.profile_id not in scoped_profiles:
            raise PermissionDeniedError(
                "This profile is not in your scope.", code="profile_out_of_scope"
            )
    a = await assignments.create(payload)
    return AssignmentRead.model_validate(a)


@router.get("", response_model=CursorPage[AssignmentRead])
async def list_assignments(
    admin: AdminUser,
    pagination: CursorPaginationDep,
    assignments: AssignmentServiceDep,
    user_id: uuid.UUID | None = None,
    profile_id: uuid.UUID | None = None,
    node_id: uuid.UUID | None = None,
    provider_kind: ProviderKind | None = None,
    status_filter: AssignmentStatus | None = None,
) -> CursorPage[AssignmentRead]:
    rows, next_cursor = await assignments.list_keyset(
        pagination,
        user_id=user_id,
        owner_id=owner_scope(admin),
        profile_id=profile_id,
        node_id=node_id,
        provider_kind=provider_kind,
        status=status_filter,
    )
    items = [AssignmentRead.model_validate(a) for a in rows]
    return CursorPage(items=items, next_cursor=next_cursor, size=pagination.size)


@router.get("/{assignment_id}", response_model=AssignmentRead)
async def get_assignment(
    assignment_id: uuid.UUID,
    admin: AdminUser,
    assignments: AssignmentServiceDep,
    users: UserServiceDep,
) -> AssignmentRead:
    a = await assignments.get(assignment_id)
    users.assert_can_manage(admin, await users.get(a.user_id))
    return AssignmentRead.model_validate(a)


@router.patch("/{assignment_id}", response_model=AssignmentRead)
async def update_assignment(
    assignment_id: uuid.UUID,
    payload: AssignmentUpdate,
    admin: WriteAdminUser,
    assignments: AssignmentServiceDep,
    users: UserServiceDep,
) -> AssignmentRead:
    existing = await assignments.get(assignment_id)
    users.assert_can_manage(admin, await users.get(existing.user_id))
    a = await assignments.update(assignment_id, payload)
    return AssignmentRead.model_validate(a)


@router.post("/{assignment_id}/disable", response_model=AssignmentRead)
async def disable_assignment(
    assignment_id: uuid.UUID,
    admin: WriteAdminUser,
    assignments: AssignmentServiceDep,
    users: UserServiceDep,
) -> AssignmentRead:
    existing = await assignments.get(assignment_id)
    users.assert_can_manage(admin, await users.get(existing.user_id))
    a = await assignments.disable(assignment_id)
    return AssignmentRead.model_validate(a)


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assignment(
    assignment_id: uuid.UUID,
    admin: WriteAdminUser,
    assignments: AssignmentServiceDep,
    users: UserServiceDep,
) -> None:
    existing = await assignments.get(assignment_id)
    users.assert_can_manage(admin, await users.get(existing.user_id))
    await assignments.delete(assignment_id)
