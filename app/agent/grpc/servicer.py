from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import grpc

from app.agent.commands import CommandSigner
from app.agent.grpc import agent_pb2 as pb
from app.agent.grpc import agent_pb2_grpc as pb_grpc
from app.agent.healing import HealingPolicy
from app.agent.ip_limit import IpLimitService
from app.agent.service import NodeAgentService
from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.core.logging import get_logger
from app.db.redis import RedisCache
from app.db.session import Database
from app.events.bus import EventBus
from app.traffic.schemas import TrafficBatch, TrafficSample

logger = get_logger("xlink.agent.grpc")


def _ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp((ms or 0) / 1000, tz=UTC)


def _token(context: grpc.aio.ServicerContext) -> str:
    for key, value in context.invocation_metadata():
        if key == "x-agent-token":
            return value
    return ""


async def _req_uuid(raw: str, context: grpc.aio.ServicerContext) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError):
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "malformed node_id")


def _maybe_uuid(raw: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError):
        return None


class NodeAgentServicer(pb_grpc.NodeAgentServicer):
    def __init__(
        self,
        db: Database,
        cache: RedisCache,
        events: EventBus,
        settings: Settings,
    ) -> None:
        self._db = db
        self._cache = cache
        self._events = events
        self._settings = settings

    def _agent_service(self, session) -> NodeAgentService:
        return NodeAgentService(
            session,
            events=self._events,
            signer=CommandSigner(self._settings.agent_signing_secret),
            cache=self._cache,
            healing_policy=HealingPolicy(enabled=self._settings.agent_self_healing_enabled),
        )

    async def _auth(self, node_id: uuid.UUID, context: grpc.aio.ServicerContext) -> None:
        token = _token(context)
        async with self._db.session() as session:
            try:
                await self._agent_service(session).authenticate(node_id, token)
            except AuthenticationError:
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid node token")

    async def GetConfig(self, request: pb.ConfigRequest, context) -> pb.DesiredConfig:
        node_id = await _req_uuid(request.node_id, context)
        token = _token(context)
        async with self._db.session() as session:
            try:
                snap = await self._agent_service(session).config_snapshot(node_id, token=token)
            except AuthenticationError:
                await context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid node token")
        return pb.DesiredConfig(
            node_id=str(snap["node_id"]),
            config_version=snap["config_version"],
            config_json=json.dumps(snap["config"]),
            assignment_count=snap["assignment_count"],
        )

    async def StreamTraffic(self, request_iterator, context):
        authed_nid = None
        async for batch in request_iterator:
            nid = await _req_uuid(batch.node_id, context)
            if authed_nid is None:
                await self._auth(nid, context)
                authed_nid = nid
            elif nid != authed_nid:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "node_id mismatch in stream")
            samples = tuple(
                TrafficSample(
                    assignment_id=aid,
                    upload_bytes=int(s.upload_bytes),
                    download_bytes=int(s.download_bytes),
                    collected_at=_ms_to_dt(s.collected_at_unix_ms),
                )
                for s in batch.samples
                if (aid := _maybe_uuid(s.assignment_id)) is not None
            )
            domain_batch = TrafficBatch(node_id=nid, batch_id=batch.batch_id, samples=samples)
            async with self._db.session() as session:
                result = await self._agent_service(session).ingest_traffic(nid, domain_batch)
            yield pb.TrafficAck(
                batch_id=result.batch_id,
                received=result.received,
                inserted=result.inserted,
                duplicates=result.duplicates,
                skipped=result.skipped,
            )

    async def StreamMetrics(self, request_iterator, context):
        authed_nid = None
        async for batch in request_iterator:
            nid = await _req_uuid(batch.node_id, context)
            if authed_nid is None:
                await self._auth(nid, context)
                authed_nid = nid
            elif nid != authed_nid:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "node_id mismatch in stream")
            samples = [
                {"name": s.name, "value": s.value, "observed_at": _ms_to_dt(s.observed_at_unix_ms)}
                for s in batch.samples
            ]
            async with self._db.session() as session:
                await self._agent_service(session).push_metrics(
                    nid, token=_token(context), samples=samples
                )
            yield pb.Ack(accepted=len(samples), dropped=0)

    async def StreamLogs(self, request_iterator, context):
        authed_nid = None
        async for batch in request_iterator:
            nid = await _req_uuid(batch.node_id, context)
            if authed_nid is None:
                await self._auth(nid, context)
                authed_nid = nid
            elif nid != authed_nid:
                await context.abort(grpc.StatusCode.PERMISSION_DENIED, "node_id mismatch in stream")
            lines = [
                {"level": ln.level, "message": ln.message, "observed_at": _ms_to_dt(ln.observed_at_unix_ms)}
                for ln in batch.lines
            ]
            async with self._db.session() as session:
                await self._agent_service(session).push_logs(
                    nid, token=_token(context), lines=lines
                )
            yield pb.Ack(accepted=len(lines), dropped=0)

    async def ReportConnections(self, request: pb.ConnectionBatch, context) -> pb.Ack:
        nid = await _req_uuid(request.node_id, context)
        await self._auth(nid, context)
        service = IpLimitService(self._db, self._cache)
        pairs = [
            (aid, s.source_ip)
            for s in request.samples
            if (aid := _maybe_uuid(s.assignment_id)) is not None
        ]
        await service.report(iter(pairs))
        return pb.Ack(accepted=len(pairs), dropped=len(request.samples) - len(pairs))

    async def ReportProviderHealth(self, request: pb.ProviderHealthBatch, context) -> pb.Ack:
        nid = await _req_uuid(request.node_id, context)
        token = _token(context)
        checks = [
            {
                "provider_name": c.provider_name,
                "status": c.status,
                "latency_ms": c.latency_ms or None,
                "detail": c.detail or None,
            }
            for c in request.checks
        ]
        async with self._db.session() as session:
            await self._agent_service(session).record_provider_health(
                nid, token=token, checks=checks
            )
        return pb.Ack(accepted=len(checks), dropped=0)

    async def ReportState(self, request: pb.ReportedState, context) -> pb.DriftReport:
        nid = await _req_uuid(request.node_id, context)
        token = _token(context)
        try:
            applied = json.loads(request.applied_json or "{}")
        except json.JSONDecodeError:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "malformed applied_json")
        if not isinstance(applied, dict):
            applied = {}
        async with self._db.session() as session:
            report = await self._agent_service(session).report_state(
                nid,
                token=token,
                config_version=request.config_version or None,
                agent_version=request.agent_version or None,
                applied=applied,
                provider_status=dict(request.provider_status),
            )
        return pb.DriftReport(
            node_id=str(report.node_id),
            severity=str(report.severity.value if hasattr(report.severity, "value") else report.severity),
            desired_version=report.desired_version,
            reported_version=report.reported_version or "",
            drift_json=json.dumps(report.drift),
            remediated=report.remediated,
        )

    async def LeaseCommands(self, request: pb.CommandLeaseRequest, context) -> pb.CommandLease:
        nid = await _req_uuid(request.node_id, context)
        token = _token(context)
        async with self._db.session() as session:
            lease_token, commands = await self._agent_service(session).lease_commands(
                nid, token=token
            )
        return pb.CommandLease(
            lease_token=lease_token or "",
            commands=[
                pb.Command(
                    command_id=str(c.id),
                    node_id=str(c.node_id),
                    kind=str(c.kind.value if hasattr(c.kind, "value") else c.kind),
                    payload_json=json.dumps(c.payload),
                    signature=c.signature,
                    origin=c.origin,
                    attempts=c.attempts,
                    max_attempts=c.max_attempts,
                )
                for c in commands
            ],
        )

    async def SubmitCommandResult(self, request: pb.CommandResult, context) -> pb.CommandResultAck:
        nid = await _req_uuid(request.node_id, context)
        command_id = await _req_uuid(request.command_id, context)
        token = _token(context)
        try:
            result = json.loads(request.result_json or "{}")
        except json.JSONDecodeError:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "malformed result_json")
        async with self._db.session() as session:
            cmd = await self._agent_service(session).report_command_result(
                nid,
                token=token,
                command_id=command_id,
                lease_token=request.lease_token,
                success=request.success,
                result=result,
            )
        status = str(cmd.status.value if hasattr(cmd.status, "value") else cmd.status)
        return pb.CommandResultAck(command_id=request.command_id, status=status)

    async def WatchEvents(self, request: pb.EventRequest, context):
        nid = await _req_uuid(request.node_id, context)
        await self._auth(nid, context)
        channel = self._cache.node_channel(nid)
        pubsub = self._cache.client.pubsub()
        await pubsub.subscribe(channel)
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=20.0)
                if msg is None:
                    continue
                data = msg["data"]
                text = data.decode() if isinstance(data, bytes) else data
                yield pb.NodeEvent(type="update", data_json=text)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
