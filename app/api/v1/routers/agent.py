from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, Query
from fastapi.responses import PlainTextResponse, StreamingResponse

from app.agent.heartbeat import NodeHeartbeatService
from app.agent.ip_limit import IpLimitService
from app.dependencies.auth import AgentIngestQuota, SudoAdminUser
from app.dependencies.core import CacheDep, DatabaseDep
from app.dependencies.services import NodeAgentServiceDep
from app.repositories.node import NodeRepository
from app.schemas.agent import (
    CommandLeaseResponse,
    CommandOut,
    CommandResultRequest,
    CommandResultResponse,
    ConnectionReportRequest,
    DesiredConfig,
    DriftReportOut,
    EnqueueCommandRequest,
    LogStreamRequest,
    MetricsStreamRequest,
    ProviderHealthReportRequest,
    ReportedStateRequest,
    StreamAck,
    TrafficReportRequest,
    TrafficReportResponse,
)
from app.traffic.schemas import TrafficBatch, TrafficSample

router = APIRouter(prefix="/agent", tags=["agent"])

_NODE_AGENT_DIR = Path(__file__).resolve().parents[4] / "node-agent"


@router.get("/install.sh", response_class=PlainTextResponse, include_in_schema=False)
async def install_script() -> PlainTextResponse:
    path = _NODE_AGENT_DIR / "install.sh"
    body = (
        path.read_text(encoding="utf-8")
        if path.exists()
        else "#!/usr/bin/env bash\necho 'installer missing'\n"
    )
    return PlainTextResponse(body, media_type="text/x-shellscript")


@router.get("/xlink-agent.py", response_class=PlainTextResponse, include_in_schema=False)
async def agent_source() -> PlainTextResponse:
    path = _NODE_AGENT_DIR / "xlink-agent.py"
    body = (
        path.read_text(encoding="utf-8") if path.exists() else "raise SystemExit('agent missing')\n"
    )
    return PlainTextResponse(body, media_type="text/x-python")


@router.post("/nodes/{node_id}/traffic", response_model=TrafficReportResponse)
async def report_traffic(
    node_id: uuid.UUID,
    payload: TrafficReportRequest,
    agent: NodeAgentServiceDep,
    _quota: AgentIngestQuota,
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
) -> TrafficReportResponse:
    batch = TrafficBatch(
        node_id=node_id,
        batch_id=payload.batch_id,
        samples=tuple(
            TrafficSample(
                assignment_id=s.assignment_id,
                upload_bytes=s.upload_bytes,
                download_bytes=s.download_bytes,
                collected_at=s.collected_at,
            )
            for s in payload.samples
        ),
    )
    result = await agent.report_traffic(node_id, token=x_agent_token, batch=batch)
    return TrafficReportResponse(
        node_id=result.node_id,
        batch_id=result.batch_id,
        received=result.received,
        inserted=result.inserted,
        duplicates=result.duplicates,
        skipped=result.skipped,
    )


@router.post("/nodes/{node_id}/connections", response_model=StreamAck)
async def report_connections(
    node_id: uuid.UUID,
    payload: ConnectionReportRequest,
    agent: NodeAgentServiceDep,
    db: DatabaseDep,
    cache: CacheDep,
    _quota: AgentIngestQuota,
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
) -> StreamAck:
    await agent.authenticate(node_id, x_agent_token)
    service = IpLimitService(db, cache)
    await service.report(((s.assignment_id, s.source_ip) for s in payload.samples), node_id=node_id)
    return StreamAck(accepted=len(payload.samples), dropped=0)


@router.get("/nodes/{node_id}/config", response_model=DesiredConfig)
async def pull_config(
    node_id: uuid.UUID,
    agent: NodeAgentServiceDep,
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    known_version: str | None = Query(default=None),
) -> DesiredConfig:
    kv = known_version or (if_none_match.strip('"') if if_none_match else None)
    snapshot = await agent.config_snapshot(node_id, token=x_agent_token, known_version=kv)
    return DesiredConfig(
        node_id=snapshot["node_id"],
        config_version=snapshot["config_version"],
        config=snapshot["config"],
        assignment_count=snapshot["assignment_count"],
        unchanged=bool(snapshot.get("unchanged", False)),
    )


@router.get("/nodes/{node_id}/events")
async def node_events(
    node_id: uuid.UUID,
    db: DatabaseDep,
    cache: CacheDep,
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
) -> StreamingResponse:
    async with db.session() as session:
        await NodeHeartbeatService(NodeRepository(session)).authenticate(node_id, x_agent_token)
    channel = cache.node_channel(node_id)

    async def stream() -> AsyncIterator[str]:
        pubsub = cache.client.pubsub()
        await pubsub.subscribe(channel)
        try:
            yield ": connected\n\n"
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=20.0)
                if msg is not None:
                    data = msg["data"]
                    yield f"data: {data.decode() if isinstance(data, bytes) else data}\n\n"
                else:
                    yield ": keepalive\n\n"
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/nodes/{node_id}/state", response_model=DriftReportOut)
async def report_state(
    node_id: uuid.UUID,
    payload: ReportedStateRequest,
    agent: NodeAgentServiceDep,
    _quota: AgentIngestQuota,
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
) -> DriftReportOut:
    report = await agent.report_state(
        node_id,
        token=x_agent_token,
        config_version=payload.config_version,
        agent_version=payload.agent_version,
        applied=payload.applied,
        provider_status=payload.provider_status,
    )
    return DriftReportOut(
        node_id=report.node_id,
        severity=report.severity,
        desired_version=report.desired_version,
        reported_version=report.reported_version,
        drift=report.drift,
        remediated=report.remediated,
    )


@router.post("/nodes/{node_id}/commands/lease", response_model=CommandLeaseResponse)
async def lease_commands(
    node_id: uuid.UUID,
    agent: NodeAgentServiceDep,
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
    limit: int = Query(default=10, ge=1, le=100),
) -> CommandLeaseResponse:
    lease_token, commands = await agent.lease_commands(node_id, token=x_agent_token, limit=limit)
    return CommandLeaseResponse(
        lease_token=lease_token if commands else None,
        commands=[
            CommandOut(
                command_id=c.id,
                node_id=c.node_id,
                kind=c.kind,
                payload=c.payload,
                signature=c.signature,
                origin=c.origin,
                attempts=c.attempts,
                max_attempts=c.max_attempts,
            )
            for c in commands
        ],
    )


@router.post("/nodes/{node_id}/commands/result", response_model=CommandResultResponse)
async def report_command_result(
    node_id: uuid.UUID,
    payload: CommandResultRequest,
    agent: NodeAgentServiceDep,
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
) -> CommandResultResponse:
    command = await agent.report_command_result(
        node_id,
        token=x_agent_token,
        command_id=payload.command_id,
        lease_token=payload.lease_token,
        success=payload.success,
        result=payload.result,
    )
    return CommandResultResponse(command_id=command.id, status=command.status.value)


@router.post("/nodes/{node_id}/provider-health", response_model=StreamAck)
async def report_provider_health(
    node_id: uuid.UUID,
    payload: ProviderHealthReportRequest,
    agent: NodeAgentServiceDep,
    _quota: AgentIngestQuota,
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
) -> StreamAck:
    count = await agent.record_provider_health(
        node_id,
        token=x_agent_token,
        checks=[c.model_dump() for c in payload.checks],
    )
    return StreamAck(accepted=count, dropped=0)


@router.post("/nodes/{node_id}/metrics", response_model=StreamAck)
async def stream_metrics(
    node_id: uuid.UUID,
    payload: MetricsStreamRequest,
    agent: NodeAgentServiceDep,
    _quota: AgentIngestQuota,
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
) -> StreamAck:
    accepted, dropped = await agent.push_metrics(
        node_id,
        token=x_agent_token,
        samples=[s.model_dump(mode="json") for s in payload.samples],
    )
    return StreamAck(accepted=accepted, dropped=dropped)


@router.post("/nodes/{node_id}/logs", response_model=StreamAck)
async def stream_logs(
    node_id: uuid.UUID,
    payload: LogStreamRequest,
    agent: NodeAgentServiceDep,
    _quota: AgentIngestQuota,
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
) -> StreamAck:
    accepted, dropped = await agent.push_logs(
        node_id,
        token=x_agent_token,
        lines=[line.model_dump(mode="json") for line in payload.lines],
    )
    return StreamAck(accepted=accepted, dropped=dropped)


@router.post("/nodes/{node_id}/commands", response_model=CommandOut, status_code=201)
async def enqueue_command(
    node_id: uuid.UUID,
    payload: EnqueueCommandRequest,
    _admin: SudoAdminUser,
    agent: NodeAgentServiceDep,
) -> CommandOut:
    command = await agent.enqueue_command(
        node_id,
        kind=payload.kind,
        payload=payload.payload,
        origin=payload.origin,
        max_attempts=payload.max_attempts,
    )
    return CommandOut(
        command_id=command.id,
        node_id=command.node_id,
        kind=command.kind,
        payload=command.payload,
        signature=command.signature,
        origin=command.origin,
        attempts=command.attempts,
        max_attempts=command.max_attempts,
    )


@router.get("/nodes/{node_id}/logs/recent", response_model=list[dict[str, Any]])
async def read_node_logs(
    node_id: uuid.UUID,
    _admin: SudoAdminUser,
    agent: NodeAgentServiceDep,
    limit: int = Query(default=100, ge=1, le=1000),
    source: str | None = Query(default=None, max_length=16),
) -> list[dict[str, Any]]:
    if source is None:
        return await agent.read_logs(node_id, limit=limit)
    rows = await agent.read_logs(node_id, limit=1000)
    matched = [r for r in rows if (r.get("source") or "xray") == source]
    return matched[:limit]


@router.get("/nodes/{node_id}/metrics/recent", response_model=list[dict[str, Any]])
async def read_node_metrics(
    node_id: uuid.UUID,
    _admin: SudoAdminUser,
    agent: NodeAgentServiceDep,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    return await agent.read_metrics(node_id, limit=limit)
