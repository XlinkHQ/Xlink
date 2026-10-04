"""The gRPC servicer is live production code — `grpc_enabled` defaults to True
and lifespan starts the server on every deployment — but it had no tests at all.

These drive the servicer directly with a fake ServicerContext, so they cover the
auth gates, the stream node_id-pinning rule, and the proto<->domain mapping
without needing a real gRPC channel.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC

import grpc
import pytest

from app.agent.grpc import agent_pb2 as pb
from app.agent.grpc.servicer import NodeAgentServicer, _maybe_uuid, _ms_to_dt
from app.agent.heartbeat import hash_agent_token
from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.providers.base.models import ProviderKind

TOKEN = "grpc-agent-token"


class _AbortedError(Exception):
    """Stands in for grpc's abort, which raises to terminate the RPC."""

    def __init__(self, code: grpc.StatusCode, details: str) -> None:
        super().__init__(details)
        self.code = code
        self.details = details


class _Context:
    """Minimal grpc.aio.ServicerContext stand-in: metadata, abort, cancellation."""

    def __init__(self, token: str | None = TOKEN, *, cancelled: bool = False) -> None:
        self._md = [("x-agent-token", token)] if token is not None else []
        self._cancelled = cancelled

    def invocation_metadata(self):
        return self._md

    async def abort(self, code, details):
        raise _AbortedError(code, details)

    def cancelled(self) -> bool:
        return self._cancelled


async def _seed(app_state: AppState) -> tuple[uuid.UUID, uuid.UUID]:
    async with app_state.db.session() as session:
        node = Node(
            name="n",
            slug=f"n-{uuid.uuid4().hex[:8]}",
            host="203.0.113.10",
            port=443,
            max_users=10,
            status=NodeStatus.ACTIVE,
            node_metadata={"agent_token_hash": hash_agent_token(TOKEN)},
        )
        session.add(node)
        await session.flush()
        user = User(
            email=f"u-{uuid.uuid4().hex[:8]}@x.io",
            username=f"u-{uuid.uuid4().hex[:8]}",
            hashed_password=hash_password("strong-password-1234-AB!"),
            role=UserRole.USER,
        )
        session.add(user)
        await session.flush()
        profile = Profile(
            name="p",
            slug=f"p-{uuid.uuid4().hex[:8]}",
            provider_kind=ProviderKind.XRAY,
            node_id=node.id,
            protocol="vless",
            settings={},
        )
        session.add(profile)
        await session.flush()
        assignment = ClientAssignment(
            user_id=user.id,
            profile_id=profile.id,
            node_id=node.id,
            provider_kind=ProviderKind.XRAY,
            status=AssignmentStatus.ACTIVE,
        )
        session.add(assignment)
        await session.flush()
        return node.id, assignment.id


@pytest.fixture
def servicer(app_state: AppState) -> NodeAgentServicer:
    return NodeAgentServicer(
        app_state.db, app_state.cache, app_state.events, app_state.settings
    )


async def _drain(agen) -> list:
    return [item async for item in agen]


async def _one_batch(batch):
    yield batch


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def test_ms_to_dt_is_utc() -> None:
    dt = _ms_to_dt(1_700_000_000_000)
    assert dt.tzinfo is UTC
    assert dt.year == 2023


def test_ms_to_dt_handles_zero() -> None:
    assert _ms_to_dt(0).tzinfo is UTC


def test_maybe_uuid_rejects_garbage_without_raising() -> None:
    assert _maybe_uuid("not-a-uuid") is None
    assert _maybe_uuid("") is None
    good = uuid.uuid4()
    assert _maybe_uuid(str(good)) == good


# --------------------------------------------------------------------------
# GetConfig
# --------------------------------------------------------------------------


async def test_get_config_returns_snapshot(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    out = await servicer.GetConfig(pb.ConfigRequest(node_id=str(node_id)), _Context())
    assert out.node_id == str(node_id)
    assert out.config_version
    json.loads(out.config_json)  # must be valid JSON


async def test_get_config_rejects_bad_token(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    with pytest.raises(_AbortedError) as e:
        await servicer.GetConfig(pb.ConfigRequest(node_id=str(node_id)), _Context("wrong"))
    assert e.value.code is grpc.StatusCode.UNAUTHENTICATED


async def test_get_config_rejects_malformed_node_id(servicer) -> None:
    with pytest.raises(_AbortedError) as e:
        await servicer.GetConfig(pb.ConfigRequest(node_id="nope"), _Context())
    assert e.value.code is grpc.StatusCode.INVALID_ARGUMENT


async def test_get_config_with_known_version_is_accepted(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    first = await servicer.GetConfig(pb.ConfigRequest(node_id=str(node_id)), _Context())
    again = await servicer.GetConfig(
        pb.ConfigRequest(node_id=str(node_id), known_version=first.config_version), _Context()
    )
    assert again.config_version == first.config_version


# --------------------------------------------------------------------------
# StreamTraffic — the ingest path
# --------------------------------------------------------------------------


def _traffic_batch(node_id, assignment_id, batch_id="g-1"):
    return pb.TrafficBatch(
        node_id=str(node_id),
        batch_id=batch_id,
        samples=[
            pb.TrafficSample(
                assignment_id=str(assignment_id),
                upload_bytes=100,
                download_bytes=200,
                collected_at_unix_ms=1_700_000_000_000,
            )
        ],
    )


async def test_stream_traffic_ingests(servicer, app_state) -> None:
    node_id, assignment_id = await _seed(app_state)
    acks = await _drain(
        servicer.StreamTraffic(_one_batch(_traffic_batch(node_id, assignment_id)), _Context())
    )
    assert len(acks) == 1
    assert acks[0].received == 1
    assert acks[0].inserted == 1


async def test_stream_traffic_is_idempotent_per_batch_id(servicer, app_state) -> None:
    """The batch claim must survive across RPCs, not just within one stream."""
    node_id, assignment_id = await _seed(app_state)
    ctx = _Context()
    await _drain(servicer.StreamTraffic(_one_batch(_traffic_batch(node_id, assignment_id)), ctx))
    again = await _drain(
        servicer.StreamTraffic(_one_batch(_traffic_batch(node_id, assignment_id)), _Context())
    )
    assert again[0].inserted == 0
    assert again[0].duplicates == 1


async def test_stream_traffic_rejects_bad_token(servicer, app_state) -> None:
    node_id, assignment_id = await _seed(app_state)
    with pytest.raises(_AbortedError) as e:
        await _drain(
            servicer.StreamTraffic(
                _one_batch(_traffic_batch(node_id, assignment_id)), _Context("wrong")
            )
        )
    assert e.value.code is grpc.StatusCode.UNAUTHENTICATED


async def test_stream_traffic_pins_the_node_id_for_the_whole_stream(servicer, app_state) -> None:
    """A stream authenticates once; a later batch must not smuggle in another
    node's id and have it accepted on the first node's credentials."""
    node_id, assignment_id = await _seed(app_state)
    other_node_id, _ = await _seed(app_state)

    async def _two():
        yield _traffic_batch(node_id, assignment_id, "g-a")
        yield _traffic_batch(other_node_id, assignment_id, "g-b")

    with pytest.raises(_AbortedError) as e:
        await _drain(servicer.StreamTraffic(_two(), _Context()))
    assert e.value.code is grpc.StatusCode.PERMISSION_DENIED


async def test_stream_traffic_drops_samples_with_unparseable_assignment_id(
    servicer, app_state
) -> None:
    node_id, _ = await _seed(app_state)
    batch = pb.TrafficBatch(
        node_id=str(node_id),
        batch_id="g-bad",
        samples=[
            pb.TrafficSample(
                assignment_id="garbage",
                upload_bytes=1,
                download_bytes=2,
                collected_at_unix_ms=1_700_000_000_000,
            )
        ],
    )
    acks = await _drain(servicer.StreamTraffic(_one_batch(batch), _Context()))
    assert acks[0].inserted == 0


# --------------------------------------------------------------------------
# StreamMetrics / StreamLogs
# --------------------------------------------------------------------------


async def test_stream_metrics_acks_each_batch(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    batch = pb.MetricBatch(
        node_id=str(node_id),
        samples=[pb.MetricSample(name="cpu", value=1.5, observed_at_unix_ms=1_700_000_000_000)],
    )
    acks = await _drain(servicer.StreamMetrics(_one_batch(batch), _Context()))
    assert acks[0].accepted == 1


async def test_stream_metrics_rejects_bad_token(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    batch = pb.MetricBatch(node_id=str(node_id), samples=[])
    with pytest.raises(_AbortedError) as e:
        await _drain(servicer.StreamMetrics(_one_batch(batch), _Context("wrong")))
    assert e.value.code is grpc.StatusCode.UNAUTHENTICATED


async def test_stream_logs_acks_each_batch(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    batch = pb.LogBatch(
        node_id=str(node_id),
        lines=[pb.LogLine(level="info", message="hi", observed_at_unix_ms=1_700_000_000_000)],
    )
    acks = await _drain(servicer.StreamLogs(_one_batch(batch), _Context()))
    assert acks[0].accepted == 1


async def test_stream_logs_pins_node_id(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    other_id, _ = await _seed(app_state)

    async def _two():
        yield pb.LogBatch(node_id=str(node_id), lines=[])
        yield pb.LogBatch(node_id=str(other_id), lines=[])

    with pytest.raises(_AbortedError) as e:
        await _drain(servicer.StreamLogs(_two(), _Context()))
    assert e.value.code is grpc.StatusCode.PERMISSION_DENIED


# --------------------------------------------------------------------------
# ReportConnections / ReportProviderHealth
# --------------------------------------------------------------------------


async def test_report_connections_counts_dropped_samples(servicer, app_state) -> None:
    node_id, assignment_id = await _seed(app_state)
    req = pb.ConnectionBatch(
        node_id=str(node_id),
        samples=[
            pb.ConnectionSample(assignment_id=str(assignment_id), source_ip="198.51.100.1"),
            pb.ConnectionSample(assignment_id="garbage", source_ip="198.51.100.2"),
        ],
    )
    ack = await servicer.ReportConnections(req, _Context())
    assert ack.accepted == 1
    assert ack.dropped == 1


async def test_report_connections_requires_auth(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    with pytest.raises(_AbortedError) as e:
        await servicer.ReportConnections(
            pb.ConnectionBatch(node_id=str(node_id), samples=[]), _Context("wrong")
        )
    assert e.value.code is grpc.StatusCode.UNAUTHENTICATED


async def test_report_provider_health(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    req = pb.ProviderHealthBatch(
        node_id=str(node_id),
        checks=[pb.ProviderHealth(provider_name="xray", status="healthy", latency_ms=12)],
    )
    ack = await servicer.ReportProviderHealth(req, _Context())
    assert ack.accepted == 1


async def test_report_provider_health_rejects_bad_token(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    with pytest.raises(_AbortedError):
        await servicer.ReportProviderHealth(
            pb.ProviderHealthBatch(node_id=str(node_id), checks=[]), _Context("wrong")
        )


# --------------------------------------------------------------------------
# ReportState
# --------------------------------------------------------------------------


async def test_report_state_returns_drift(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    req = pb.ReportedState(
        node_id=str(node_id),
        config_version="v-old",
        agent_version="1.2.3",
        applied_json=json.dumps({"xray": {"version": "1"}}),
        provider_status={"xray": "healthy"},
    )
    out = await servicer.ReportState(req, _Context())
    assert out.node_id == str(node_id)
    json.loads(out.drift_json)


async def test_report_state_rejects_malformed_applied_json(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    req = pb.ReportedState(node_id=str(node_id), applied_json="{not json")
    with pytest.raises(_AbortedError) as e:
        await servicer.ReportState(req, _Context())
    assert e.value.code is grpc.StatusCode.INVALID_ARGUMENT


async def test_report_state_tolerates_non_dict_applied_json(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    req = pb.ReportedState(node_id=str(node_id), applied_json="[1,2,3]")
    out = await servicer.ReportState(req, _Context())
    assert out.node_id == str(node_id)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


async def test_lease_commands_when_none_pending(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    out = await servicer.LeaseCommands(pb.CommandLeaseRequest(node_id=str(node_id)), _Context())
    assert list(out.commands) == []


async def test_lease_commands_returns_enqueued_command(servicer, app_state) -> None:
    from app.agent.commands import CommandSigner
    from app.agent.domain import CommandKind
    from app.agent.healing import HealingPolicy
    from app.agent.service import NodeAgentService

    node_id, _ = await _seed(app_state)
    async with app_state.db.session() as session:
        svc = NodeAgentService(
            session,
            events=app_state.events,
            signer=CommandSigner(app_state.settings.agent_signing_secret),
            cache=app_state.cache,
            healing_policy=HealingPolicy(enabled=False),
        )
        await svc.authenticate(node_id, TOKEN)
        await svc.enqueue_command(node_id, kind=CommandKind.RESTART, payload={})

    out = await servicer.LeaseCommands(pb.CommandLeaseRequest(node_id=str(node_id)), _Context())
    assert len(out.commands) == 1
    assert out.lease_token
    cmd = out.commands[0]
    assert cmd.node_id == str(node_id)
    json.loads(cmd.payload_json)


async def test_submit_command_result_rejects_malformed_json(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    req = pb.CommandResult(
        node_id=str(node_id),
        command_id=str(uuid.uuid4()),
        lease_token="t",
        success=True,
        result_json="{broken",
    )
    with pytest.raises(_AbortedError) as e:
        await servicer.SubmitCommandResult(req, _Context())
    assert e.value.code is grpc.StatusCode.INVALID_ARGUMENT


async def test_submit_command_result_rejects_malformed_command_id(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    req = pb.CommandResult(node_id=str(node_id), command_id="nope", result_json="{}")
    with pytest.raises(_AbortedError) as e:
        await servicer.SubmitCommandResult(req, _Context())
    assert e.value.code is grpc.StatusCode.INVALID_ARGUMENT


# --------------------------------------------------------------------------
# WatchEvents
# --------------------------------------------------------------------------


async def test_watch_events_requires_auth(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    with pytest.raises(_AbortedError) as e:
        await _drain(servicer.WatchEvents(pb.EventRequest(node_id=str(node_id)), _Context("wrong")))
    assert e.value.code is grpc.StatusCode.UNAUTHENTICATED


async def test_watch_events_stops_when_context_is_cancelled(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    events = await _drain(
        servicer.WatchEvents(pb.EventRequest(node_id=str(node_id)), _Context(cancelled=True))
    )
    assert events == []


# --------------------------------------------------------------------------
# Regression guard: every token-passing RPC must map a bad token to
# UNAUTHENTICATED rather than letting AuthenticationError escape as UNKNOWN.
# --------------------------------------------------------------------------


async def test_report_state_rejects_bad_token(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    req = pb.ReportedState(node_id=str(node_id), applied_json="{}")
    with pytest.raises(_AbortedError) as e:
        await servicer.ReportState(req, _Context("wrong"))
    assert e.value.code is grpc.StatusCode.UNAUTHENTICATED


async def test_lease_commands_rejects_bad_token(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    with pytest.raises(_AbortedError) as e:
        await servicer.LeaseCommands(
            pb.CommandLeaseRequest(node_id=str(node_id)), _Context("wrong")
        )
    assert e.value.code is grpc.StatusCode.UNAUTHENTICATED


async def test_submit_command_result_rejects_bad_token(servicer, app_state) -> None:
    node_id, _ = await _seed(app_state)
    req = pb.CommandResult(
        node_id=str(node_id),
        command_id=str(uuid.uuid4()),
        lease_token="t",
        success=True,
        result_json="{}",
    )
    with pytest.raises(_AbortedError) as e:
        await servicer.SubmitCommandResult(req, _Context("wrong"))
    assert e.value.code is grpc.StatusCode.UNAUTHENTICATED
