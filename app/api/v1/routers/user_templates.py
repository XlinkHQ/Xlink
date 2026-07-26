from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.core.exceptions import ConflictError, NotFoundError
from app.dependencies.auth import AdminUser, WriteAdminUser
from app.dependencies.core import SessionDep
from app.domain.user_template import UserTemplate
from app.schemas.user_template import (
    UserTemplateCreate,
    UserTemplateRead,
    UserTemplateUpdate,
)

router = APIRouter(prefix="/user-templates", tags=["user-templates"])


@router.get("", response_model=list[UserTemplateRead])
async def list_templates(_admin: AdminUser, session: SessionDep) -> list[UserTemplateRead]:
    rows = (await session.execute(select(UserTemplate).order_by(UserTemplate.name))).scalars().all()
    return [UserTemplateRead.model_validate(t) for t in rows]


@router.post("", response_model=UserTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: UserTemplateCreate,
    _admin: WriteAdminUser,
    session: SessionDep,
) -> UserTemplateRead:
    exists = (
        (await session.execute(select(UserTemplate).where(UserTemplate.name == payload.name)))
        .scalars()
        .first()
    )
    if exists is not None:
        raise ConflictError("A template with this name already exists.", code="template_exists")
    tpl = UserTemplate(
        name=payload.name,
        data_limit_bytes=payload.data_limit_bytes,
        expire_days=payload.expire_days,
        data_reset_strategy=payload.data_reset_strategy,
        device_limit=payload.device_limit,
        username_prefix=payload.username_prefix,
    )
    session.add(tpl)
    await session.flush()
    return UserTemplateRead.model_validate(tpl)


@router.patch("/{template_id}", response_model=UserTemplateRead)
async def update_template(
    template_id: uuid.UUID,
    payload: UserTemplateUpdate,
    _admin: WriteAdminUser,
    session: SessionDep,
) -> UserTemplateRead:
    tpl = await session.get(UserTemplate, template_id)
    if tpl is None:
        raise NotFoundError("Template not found.", code="template_not_found")
    for field in (
        "name",
        "data_limit_bytes",
        "expire_days",
        "data_reset_strategy",
        "device_limit",
        "username_prefix",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(tpl, field, value)
    await session.flush()
    return UserTemplateRead.model_validate(tpl)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID,
    _admin: WriteAdminUser,
    session: SessionDep,
) -> None:
    tpl = await session.get(UserTemplate, template_id)
    if tpl is None:
        raise NotFoundError("Template not found.", code="template_not_found")
    await session.delete(tpl)
    await session.flush()
