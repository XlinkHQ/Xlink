from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import Field

from app.agent.domain import CommandKind, NodeCommand
from app.core.exceptions import NotFoundError
from app.dependencies.auth import SudoAdminUser
from app.dependencies.core import SessionDep
from app.dependencies.services import NodeAgentServiceDep
from app.schemas.base import APIModel, InputModel
from app.services import reality_scan

router = APIRouter(prefix="/reality", tags=["reality"])


class RealityScanRequest(InputModel):
    targets: list[str] = Field(min_length=1, max_length=reality_scan.MAX_TARGETS)


class RealityScanItem(APIModel):
    target: str
    port: int
    ip: str | None
    ok: bool
    tls13: bool
    h2: bool
    x25519: bool | None
    cert_valid: bool
    latency_ms: float | None
    issuer: str | None
    problems: list[str]


@router.post("/scan", response_model=list[RealityScanItem])
async def scan_targets(payload: RealityScanRequest, _admin: SudoAdminUser) -> list[RealityScanItem]:
    results = await reality_scan.scan(payload.targets)
    return [RealityScanItem.model_validate(r.as_dict()) for r in results]


class NodeScanQueued(APIModel):
    command_id: uuid.UUID


class NodeScanStatus(APIModel):
    status: str
    results: list[RealityScanItem] = Field(default_factory=list)
    error: str | None = None


@router.post("/scan/node/{node_id}", response_model=NodeScanQueued, status_code=202)
async def scan_from_node(
    node_id: uuid.UUID,
    payload: RealityScanRequest,
    _admin: SudoAdminUser,
    agent: NodeAgentServiceDep,
) -> NodeScanQueued:
    """Queue the scan on the node itself. What matters for REALITY is how the
    target looks from the node's network (latency, blocking, routing), which
    the panel host cannot see. The agent runs it on its next command poll."""
    command = await agent.enqueue_command(
        node_id,
        kind="reality_scan",
        payload={"targets": payload.targets},
        origin="reality_scan",
        max_attempts=1,
    )
    return NodeScanQueued(command_id=command.id)


@router.get("/scan/commands/{command_id}", response_model=NodeScanStatus)
async def node_scan_status(
    command_id: uuid.UUID, _admin: SudoAdminUser, session: SessionDep
) -> NodeScanStatus:
    command = await session.get(NodeCommand, command_id)
    if command is None or command.kind != CommandKind.REALITY_SCAN:
        raise NotFoundError("Scan not found.", code="scan_not_found")
    result = command.result or {}
    items = [
        RealityScanItem.model_validate(r)
        for r in result.get("results") or []
        if isinstance(r, dict)
    ]
    return NodeScanStatus(
        status=str(command.status.value), results=items, error=result.get("error")
    )
