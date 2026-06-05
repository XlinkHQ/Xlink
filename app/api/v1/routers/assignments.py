from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.dependencies.auth import AdminUser
from app.dependencies.pagination import CursorPaginationDep
from app.dependencies.services import AssignmentServiceDep
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
    _admin: AdminUser,
    assignments: AssignmentServiceDep,
) -> AssignmentRead:
    a = await assignments.create(payload)
    return AssignmentRead.model_validate(a)


@router.get("", response_model=CursorPage[AssignmentRead])
async def list_assignments(
    _admin: AdminUser,
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
    _admin: AdminUser,
    assignments: AssignmentServiceDep,
) -> AssignmentRead:
    a = await assignments.get(assignment_id)
    return AssignmentRead.model_validate(a)


@router.patch("/{assignment_id}", response_model=AssignmentRead)
async def update_assignment(
    assignment_id: uuid.UUID,
    payload: AssignmentUpdate,
    _admin: AdminUser,
    assignments: AssignmentServiceDep,
) -> AssignmentRead:
    a = await assignments.update(assignment_id, payload)
    return AssignmentRead.model_validate(a)


@router.post("/{assignment_id}/disable", response_model=AssignmentRead)
async def disable_assignment(
    assignment_id: uuid.UUID,
    _admin: AdminUser,
    assignments: AssignmentServiceDep,
) -> AssignmentRead:
    a = await assignments.disable(assignment_id)
    return AssignmentRead.model_validate(a)


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assignment(
    assignment_id: uuid.UUID,
    _admin: AdminUser,
    assignments: AssignmentServiceDep,
) -> None:
    await assignments.delete(assignment_id)
