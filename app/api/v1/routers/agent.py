from __future__ import annotations

import uuid

from fastapi import APIRouter, Header

from app.dependencies.auth import AdminUser
from app.dependencies.services import NodeAgentServiceDep
from app.schemas.agent import (
    CommandLeaseResponse,
    CommandOut,
    CommandResultRequest,
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


@router.post("/nodes/{node_id}/traffic", response_model=TrafficReportResponse)
async def report_traffic(
    node_id: uuid.UUID,
    payload: TrafficReportRequest,
    agent: NodeAgentServiceDep,
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


@router.get("/nodes/{node_id}/config", response_model=DesiredConfig)
async def pull_config(
    node_id: uuid.UUID,
    agent: NodeAgentServiceDep,
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
) -> DesiredConfig:
    snapshot = await agent.config_snapshot(node_id, token=x_agent_token)
    return DesiredConfig(
        node_id=snapshot["node_id"],
        config_version=snapshot["config_version"],
        config=snapshot["config"],
        assignment_count=snapshot["assignment_count"],
    )


@router.post("/nodes/{node_id}/state", response_model=DriftReportOut)
async def report_state(
    node_id: uuid.UUID,
    payload: ReportedStateRequest,
    agent: NodeAgentServiceDep,
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
        severity=report.severity.value,
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
    limit: int = 10,
) -> CommandLeaseResponse:
    lease_token, commands = await agent.lease_commands(node_id, token=x_agent_token, limit=limit)
    return CommandLeaseResponse(
        lease_token=lease_token if commands else None,
        commands=[
            CommandOut(
                command_id=c.id,
                node_id=c.node_id,
                kind=c.kind.value,
                payload=c.payload,
                signature=c.signature,
                origin=c.origin,
                attempts=c.attempts,
                max_attempts=c.max_attempts,
            )
            for c in commands
        ],
    )


@router.post("/nodes/{node_id}/commands/result")
async def report_command_result(
    node_id: uuid.UUID,
    payload: CommandResultRequest,
    agent: NodeAgentServiceDep,
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
) -> dict[str, str]:
    command = await agent.report_command_result(
        node_id,
        token=x_agent_token,
        command_id=payload.command_id,
        lease_token=payload.lease_token,
        success=payload.success,
        result=payload.result,
    )
    return {"command_id": str(command.id), "status": command.status.value}


@router.post("/nodes/{node_id}/provider-health", response_model=StreamAck)
async def report_provider_health(
    node_id: uuid.UUID,
    payload: ProviderHealthReportRequest,
    agent: NodeAgentServiceDep,
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
    _admin: AdminUser,
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
        kind=command.kind.value,
        payload=command.payload,
        signature=command.signature,
        origin=command.origin,
        attempts=command.attempts,
        max_attempts=command.max_attempts,
    )
