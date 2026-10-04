from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core import rbac
from app.core.exceptions import ConflictError, NotFoundError
from app.dependencies.auth import SudoAdminUser
from app.dependencies.core import SessionDep
from app.domain.admin_role import AdminRole
from app.domain.user import User
from app.schemas.admin_role import (
    AdminRoleCreate,
    AdminRoleRead,
    AdminRoleUpdate,
    RoleCatalogueRead,
)

router = APIRouter(prefix="/admin-roles", tags=["admin-roles"])


@router.get("/catalogue", response_model=RoleCatalogueRead)
async def role_catalogue(_admin: SudoAdminUser) -> RoleCatalogueRead:
    return RoleCatalogueRead(
        resources={k: sorted(v) for k, v in rbac.CATALOGUE.items()},
        limits=sorted(rbac.LIMIT_KEYS),
        scopes={s.name.lower(): int(s) for s in rbac.Scope},
    )


@router.get("", response_model=list[AdminRoleRead])
async def list_roles(_admin: SudoAdminUser, session: SessionDep) -> list[AdminRoleRead]:
    rows = (await session.execute(select(AdminRole).order_by(AdminRole.name))).scalars().all()
    return [AdminRoleRead.model_validate(r) for r in rows]


@router.post("", response_model=AdminRoleRead, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: AdminRoleCreate, _admin: SudoAdminUser, session: SessionDep
) -> AdminRoleRead:
    rbac.validate_role_payload(payload.permissions, payload.limits)
    role = AdminRole(
        name=payload.name.strip(),
        description=payload.description,
        permissions=payload.permissions,
        limits=payload.limits,
    )
    session.add(role)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("A role with that name exists.", code="admin_role_exists") from exc
    await session.refresh(role)
    return AdminRoleRead.model_validate(role)


async def _get(session, role_id: uuid.UUID) -> AdminRole:  # noqa: ANN001
    role = await session.get(AdminRole, role_id)
    if role is None:
        raise NotFoundError("Admin role not found.", code="admin_role_not_found")
    return role


@router.patch("/{role_id}", response_model=AdminRoleRead)
async def update_role(
    role_id: uuid.UUID, payload: AdminRoleUpdate, _admin: SudoAdminUser, session: SessionDep
) -> AdminRoleRead:
    role = await _get(session, role_id)
    permissions = payload.permissions if payload.permissions is not None else role.permissions
    limits = payload.limits if payload.limits is not None else role.limits
    rbac.validate_role_payload(permissions, limits)
    if payload.name is not None:
        role.name = payload.name.strip()
    if payload.description is not None:
        role.description = payload.description
    role.permissions = permissions
    role.limits = limits
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("A role with that name exists.", code="admin_role_exists") from exc
    await session.refresh(role)
    return AdminRoleRead.model_validate(role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(role_id: uuid.UUID, _admin: SudoAdminUser, session: SessionDep) -> None:
    role = await _get(session, role_id)
    in_use = await session.scalar(
        select(func.count()).select_from(User).where(User.admin_role_id == role_id)
    )
    if in_use:
        # The FK is ON DELETE SET NULL, which would silently drop those admins
        # back to the (often broader) legacy rules. Make the operator choose.
        raise ConflictError(
            f"Role is assigned to {in_use} admin(s); reassign them first.",
            code="admin_role_in_use",
        )
    await session.delete(role)
