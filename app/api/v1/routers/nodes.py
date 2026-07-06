from __future__ import annotations

import uuid

from datetime import datetime

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.dependencies.auth import AdminUser, SudoAdminUser
from app.dependencies.core import CacheDep
from app.dependencies.pagination import CursorPaginationDep
from app.dependencies.services import NodeAgentServiceDep, NodeServiceDep
from app.domain.node import NodeStatus
from app.schemas.node import (
    NodeCreate,
    NodeHeartbeat,
    NodeRead,
    NodeStatusUpdate,
    NodeUpdate,
)
from app.schemas.pagination import CursorPage
from app.services.xray_releases import XrayReleaseService

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("/xray-versions", response_model=list[str])
async def xray_versions(_admin: AdminUser, cache: CacheDep) -> list[str]:
    return await XrayReleaseService(cache).versions()


@router.post("", response_model=NodeRead, status_code=status.HTTP_201_CREATED)
async def create_node(
    payload: NodeCreate,
    _admin: SudoAdminUser,
    nodes: NodeServiceDep,
) -> NodeRead:
    node = await nodes.create(payload)
    return NodeRead.model_validate(node)


@router.get("", response_model=CursorPage[NodeRead])
async def list_nodes(
    _admin: AdminUser,
    pagination: CursorPaginationDep,
    nodes: NodeServiceDep,
    status_filter: NodeStatus | None = None,
) -> CursorPage[NodeRead]:
    rows, next_cursor = await nodes.list_nodes_keyset(pagination, status=status_filter)
    items = [NodeRead.model_validate(n) for n in rows]
    return CursorPage(items=items, next_cursor=next_cursor, size=pagination.size)


@router.get("/{node_id}", response_model=NodeRead)
async def get_node(
    node_id: uuid.UUID,
    _admin: AdminUser,
    nodes: NodeServiceDep,
) -> NodeRead:
    node = await nodes.get(node_id)
    return NodeRead.model_validate(node)


class CoreHealthRead(BaseModel):
    provider_name: str
    status: str
    latency_ms: float | None = None
    detail: str | None = None
    checked_at: datetime


@router.get("/{node_id}/cores", response_model=list[CoreHealthRead])
async def node_core_health(
    node_id: uuid.UUID,
    _admin: AdminUser,
    nodes: NodeServiceDep,
    agent: NodeAgentServiceDep,
) -> list[CoreHealthRead]:
    await nodes.get(node_id)  # 404 if the node does not exist
    rows = await agent.provider_health(node_id)
    return [
        CoreHealthRead(
            provider_name=r.provider_name,
            status=r.status.value,
            latency_ms=r.latency_ms,
            detail=r.detail,
            checked_at=r.checked_at,
        )
        for r in rows
    ]


@router.patch("/{node_id}", response_model=NodeRead)
async def update_node(
    node_id: uuid.UUID,
    payload: NodeUpdate,
    _admin: SudoAdminUser,
    nodes: NodeServiceDep,
) -> NodeRead:
    node = await nodes.update(node_id, payload)
    return NodeRead.model_validate(node)


@router.post("/{node_id}/status", response_model=NodeRead)
async def set_node_status(
    node_id: uuid.UUID,
    payload: NodeStatusUpdate,
    _admin: SudoAdminUser,
    nodes: NodeServiceDep,
) -> NodeRead:
    node = await nodes.set_status(node_id, payload.status)
    return NodeRead.model_validate(node)


@router.post("/{node_id}/disable", response_model=NodeRead)
async def disable_node(
    node_id: uuid.UUID,
    _admin: SudoAdminUser,
    nodes: NodeServiceDep,
) -> NodeRead:
    node = await nodes.disable(node_id)
    return NodeRead.model_validate(node)


@router.post("/{node_id}/restart-core", response_model=NodeRead)
async def restart_node_core(
    node_id: uuid.UUID,
    _admin: SudoAdminUser,
    nodes: NodeServiceDep,
    cache: CacheDep,
) -> NodeRead:
    node = await nodes.restart_core(node_id)

    await cache.publish_node_event(node_id, "config_changed")
    return NodeRead.model_validate(node)


@router.post("/{node_id}/heartbeat", response_model=NodeRead)
async def node_heartbeat(
    node_id: uuid.UUID,
    payload: NodeHeartbeat,
    _admin: SudoAdminUser,
    nodes: NodeServiceDep,
) -> NodeRead:
    node = await nodes.heartbeat(node_id, payload.current_users, payload.status)
    return NodeRead.model_validate(node)


@router.post("/{node_id}/agent-token")
async def provision_agent_token(
    node_id: uuid.UUID,
    _admin: SudoAdminUser,
    nodes: NodeServiceDep,
) -> dict[str, str]:
    token = await nodes.provision_agent_token(node_id)
    return {"node_id": str(node_id), "agent_token": token}


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    node_id: uuid.UUID,
    _admin: SudoAdminUser,
    nodes: NodeServiceDep,
) -> None:
    await nodes.delete(node_id)
