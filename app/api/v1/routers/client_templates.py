from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, NotFoundError
from app.dependencies.auth import SudoAdminUser
from app.dependencies.core import SessionDep
from app.dependencies.services import SubscriptionServiceDep
from app.domain.client_template import ClientTemplate
from app.schemas.client_template import (
    ClientTemplateCreate,
    ClientTemplateRead,
    ClientTemplateUpdate,
)
from app.subscription import templates as client_templates

router = APIRouter(prefix="/client-templates", tags=["client-templates"])


async def _clear_default(session, fmt: str, keep: uuid.UUID | None) -> None:  # noqa: ANN001
    stmt = update(ClientTemplate).where(
        ClientTemplate.format == fmt, ClientTemplate.is_default.is_(True)
    )
    if keep is not None:
        stmt = stmt.where(ClientTemplate.id != keep)
    await session.execute(stmt.values(is_default=False))


async def _get(session, template_id: uuid.UUID) -> ClientTemplate:  # noqa: ANN001
    row = await session.get(ClientTemplate, template_id)
    if row is None:
        raise NotFoundError("Client template not found.", code="client_template_not_found")
    return row


@router.get("", response_model=list[ClientTemplateRead])
async def list_templates(_admin: SudoAdminUser, session: SessionDep) -> list[ClientTemplateRead]:
    rows = (
        (
            await session.execute(
                select(ClientTemplate).order_by(ClientTemplate.format, ClientTemplate.name)
            )
        )
        .scalars()
        .all()
    )
    return [ClientTemplateRead.model_validate(r) for r in rows]


@router.post("", response_model=ClientTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: ClientTemplateCreate,
    _admin: SudoAdminUser,
    session: SessionDep,
    subscriptions: SubscriptionServiceDep,
) -> ClientTemplateRead:
    client_templates.parse(payload.format, payload.content)
    row = ClientTemplate(
        name=payload.name.strip(),
        format=payload.format,
        content=payload.content,
        is_default=payload.is_default,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "A template with that name exists.", code="client_template_exists"
        ) from exc
    if row.is_default:
        await _clear_default(session, row.format, keep=row.id)
        await subscriptions.invalidate_cache()
    await session.refresh(row)
    return ClientTemplateRead.model_validate(row)


@router.patch("/{template_id}", response_model=ClientTemplateRead)
async def update_template(
    template_id: uuid.UUID,
    payload: ClientTemplateUpdate,
    _admin: SudoAdminUser,
    session: SessionDep,
    subscriptions: SubscriptionServiceDep,
) -> ClientTemplateRead:
    row = await _get(session, template_id)
    was_default = row.is_default
    if payload.content is not None:
        client_templates.parse(row.format, payload.content)
        row.content = payload.content
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.is_default is not None:
        row.is_default = payload.is_default
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "A template with that name exists.", code="client_template_exists"
        ) from exc
    if row.is_default:
        await _clear_default(session, row.format, keep=row.id)
    if row.is_default or was_default:
        await subscriptions.invalidate_cache()
    await session.refresh(row)
    return ClientTemplateRead.model_validate(row)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID,
    _admin: SudoAdminUser,
    session: SessionDep,
    subscriptions: SubscriptionServiceDep,
) -> None:
    row = await _get(session, template_id)
    was_default = row.is_default
    await session.delete(row)
    await session.flush()
    if was_default:
        await subscriptions.invalidate_cache()
