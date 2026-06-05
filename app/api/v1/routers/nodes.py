from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.dependencies.auth import AdminUser
from app.dependencies.pagination import CursorPaginationDep
from app.dependencies.services import NodeServiceDep
from app.domain.node import NodeStatus
from app.schemas.node import (
    NodeCreate,
    NodeHeartbeat,
    NodeRead,
    NodeStatusUpdate,
    NodeUpdate,
)
from app.schemas.pagination import CursorPage

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.post("", response_model=NodeRead, status_code=status.HTTP_201_CREATED)
async def create_node(
    payload: NodeCreate,
    _admin: AdminUser,
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


@router.patch("/{node_id}", response_model=NodeRead)
async def update_node(
    node_id: uuid.UUID,
    payload: NodeUpdate,
    _admin: AdminUser,
    nodes: NodeServiceDep,
) -> NodeRead:
    node = await nodes.update(node_id, payload)
    return NodeRead.model_validate(node)


@router.post("/{node_id}/status", response_model=NodeRead)
async def set_node_status(
    node_id: uuid.UUID,
    payload: NodeStatusUpdate,
    _admin: AdminUser,
    nodes: NodeServiceDep,
) -> NodeRead:
    node = await nodes.set_status(node_id, payload.status)
    return NodeRead.model_validate(node)


@router.post("/{node_id}/disable", response_model=NodeRead)
async def disable_node(
    node_id: uuid.UUID,
    _admin: AdminUser,
    nodes: NodeServiceDep,
) -> NodeRead:
    node = await nodes.disable(node_id)
    return NodeRead.model_validate(node)


@router.post("/{node_id}/heartbeat", response_model=NodeRead)
async def node_heartbeat(
    node_id: uuid.UUID,
    payload: NodeHeartbeat,
    _admin: AdminUser,
    nodes: NodeServiceDep,
) -> NodeRead:
    node = await nodes.heartbeat(node_id, payload.current_users, payload.status)
    return NodeRead.model_validate(node)
