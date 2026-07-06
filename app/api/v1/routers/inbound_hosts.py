from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.dependencies.auth import AdminUser, SudoAdminUser
from app.dependencies.services import InboundHostServiceDep
from app.schemas.inbound_host import InboundHostCreate, InboundHostRead, InboundHostUpdate

router = APIRouter(prefix="/inbound-hosts", tags=["inbound-hosts"])


@router.post("", response_model=InboundHostRead, status_code=status.HTTP_201_CREATED)
async def create_host(
    payload: InboundHostCreate,
    _admin: SudoAdminUser,
    hosts: InboundHostServiceDep,
) -> InboundHostRead:
    return InboundHostRead.model_validate(await hosts.create(payload))


@router.get("", response_model=list[InboundHostRead])
async def list_hosts(
    _admin: AdminUser,
    hosts: InboundHostServiceDep,
    profile_id: uuid.UUID | None = None,
) -> list[InboundHostRead]:
    rows = await hosts.list(profile_id)
    return [InboundHostRead.model_validate(h) for h in rows]


@router.get("/{host_id}", response_model=InboundHostRead)
async def get_host(
    host_id: uuid.UUID,
    _admin: AdminUser,
    hosts: InboundHostServiceDep,
) -> InboundHostRead:
    return InboundHostRead.model_validate(await hosts.get(host_id))


@router.patch("/{host_id}", response_model=InboundHostRead)
async def update_host(
    host_id: uuid.UUID,
    payload: InboundHostUpdate,
    _admin: SudoAdminUser,
    hosts: InboundHostServiceDep,
) -> InboundHostRead:
    return InboundHostRead.model_validate(await hosts.update(host_id, payload))


@router.delete("/{host_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_host(
    host_id: uuid.UUID,
    _admin: SudoAdminUser,
    hosts: InboundHostServiceDep,
) -> None:
    await hosts.delete(host_id)
