from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.agent.commands import CommandSigner
from app.agent.config_sync import ConfigSyncService, config_version
from app.agent.domain import CommandStatus, DriftSeverity, ProviderHealthStatus
from app.agent.healing import HealingPolicy
from app.agent.heartbeat import hash_agent_token
from app.agent.service import NodeAgentService
from app.core.exceptions import AuthenticationError, ValidationError
from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.providers.base.models import ProviderKind

TOKEN = "agent-token-advanced"
SECRET = "agent-signing-secret-32-chars-minimum-x"


def _signer() -> CommandSigner:
    return CommandSigner(SECRET)


async def _seed(
    app_state: AppState, *, active_assignments: int = 1
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    async with app_state.db.session() as session:
        node = Node(
            name=f"n-{uuid.uuid4().hex[:8]}",
            slug=f"n-{uuid.uuid4().hex[:8]}",
            host="203.0.113.7",
            port=443,
            max_users=100,
            status=NodeStatus.ACTIVE,
            node_metadata={"agent_token_hash": hash_agent_token(TOKEN)},
        )
        session.add(node)
        await session.flush()
        user = User(
            email=f"u-{uuid.uuid4().hex[:8]}@x.io",
            username=f"u-{uuid.uuid4().hex[:8]}",
            hashed_password=hash_password("strong-password-1234"),
            role=UserRole.USER,
        )
        session.add(user)
        await session.flush()
        assignment_ids = []
        for _ in range(active_assignments):
            profile = Profile(
                name="p",
                slug=f"p-{uuid.uuid4().hex[:8]}",
                provider_kind=ProviderKind.XRAY,
                node_id=node.id,
                protocol="vless",
                settings={"flow": "vision"},
            )
            session.add(profile)
            await session.flush()
            assignment = ClientAssignment(
                user_id=user.id,
                profile_id=profile.id,
                node_id=node.id,
                provider_kind=ProviderKind.XRAY,
                provider_client_id=str(uuid.uuid4()),
                status=AssignmentStatus.ACTIVE,
            )
            session.add(assignment)
            await session.flush()
            assignment_ids.append(assignment.id)
        return node.id, assignment_ids


def _svc(app_state: AppState, session, *, healing=True) -> NodeAgentService:
    return NodeAgentService(
        session,
        events=app_state.events,
        signer=_signer(),
        cache=app_state.cache,
        healing_policy=HealingPolicy(enabled=healing),
    )


async def test_config_sync_versioned_snapshot(app_state: AppState):
    node_id, _ = await _seed(app_state, active_assignments=2)
    async with app_state.db.session() as session:
        snap = await _svc(app_state, session).config_snapshot(node_id, token=TOKEN)
    assert snap["assignment_count"] == 2
    assert len(snap["config_version"]) == 32
    expected = config_version(snap["config"])
    assert snap["config_version"] == expected


async def test_config_sync_bad_token(app_state: AppState):
    node_id, _ = await _seed(app_state)
    async with app_state.db.session() as session:
        with pytest.raises(AuthenticationError):
            await _svc(app_state, session).config_snapshot(node_id, token="wrong")


async def test_state_report_no_drift_when_synced(app_state: AppState):
    node_id, _ = await _seed(app_state)
    async with app_state.db.session() as session:
        svc = _svc(app_state, session)
        snap = await svc.config_snapshot(node_id, token=TOKEN)
    async with app_state.db.session() as session:
        svc = _svc(app_state, session)
        report = await svc.report_state(
            node_id,
            token=TOKEN,
            config_version=snap["config_version"],
            agent_version="1.0.0",
            applied=snap["config"],
            provider_status={"xray": "healthy"},
        )
    assert report.severity is DriftSeverity.NONE
    assert report.remediated is False


async def test_drift_detection_high_when_never_reported(app_state: AppState):
    node_id, _ = await _seed(app_state, active_assignments=2)
    async with app_state.db.session() as session:
        node = await session.get(Node, node_id)
        report = await ConfigSyncService(session).detect_drift(node)
    assert report.severity is DriftSeverity.HIGH


async def test_self_healing_enqueues_apply_config(app_state: AppState):
    node_id, _ = await _seed(app_state, active_assignments=3)
    async with app_state.db.session() as session:
        svc = _svc(app_state, session)
        report = await svc.report_state(
            node_id,
            token=TOKEN,
            config_version="stale-version",
            agent_version="1.0.0",
            applied={},
            provider_status={},
        )
    assert report.severity in (DriftSeverity.MEDIUM, DriftSeverity.HIGH)
    assert report.remediated is True
    async with app_state.db.session() as session:
        _, commands = await _svc(app_state, session).lease_commands(node_id, token=TOKEN)
    assert len(commands) == 1
    assert commands[0].kind.value == "apply_config"
    assert commands[0].payload["config_version"] == report.desired_version


async def test_command_signature_verifies(app_state: AppState):
    node_id, _ = await _seed(app_state)
    async with app_state.db.session() as session:
        command = await _svc(app_state, session).enqueue_command(
            node_id, kind="reload", payload={}, origin="operator"
        )
    signer = _signer()
    assert signer.verify(
        command.id,
        node_id,
        "reload",
        {},
        command.signature,
        node_token_hash=hash_agent_token(TOKEN),
    )


async def test_command_kind_allowlist(app_state: AppState):
    node_id, _ = await _seed(app_state)
    async with app_state.db.session() as session:
        with pytest.raises(ValidationError):
            await _svc(app_state, session).enqueue_command(
                node_id, kind="rm_rf_slash", payload={}, origin="operator"
            )


async def test_command_lease_and_result(app_state: AppState):
    node_id, _ = await _seed(app_state)
    async with app_state.db.session() as session:
        await _svc(app_state, session).enqueue_command(
            node_id, kind="restart", payload={}, origin="operator"
        )
    async with app_state.db.session() as session:
        lease_token, commands = await _svc(app_state, session).lease_commands(node_id, token=TOKEN)
    assert commands[0].status is CommandStatus.LEASED
    async with app_state.db.session() as session:
        done = await _svc(app_state, session).report_command_result(
            node_id,
            token=TOKEN,
            command_id=commands[0].id,
            lease_token=lease_token,
            success=True,
            result={"ok": True},
        )
    assert done.status is CommandStatus.SUCCEEDED


async def test_command_result_bad_lease(app_state: AppState):
    node_id, _ = await _seed(app_state)
    async with app_state.db.session() as session:
        await _svc(app_state, session).enqueue_command(
            node_id, kind="restart", payload={}, origin="operator"
        )
    async with app_state.db.session() as session:
        _, commands = await _svc(app_state, session).lease_commands(node_id, token=TOKEN)
    async with app_state.db.session() as session:
        with pytest.raises(ValidationError):
            await _svc(app_state, session).report_command_result(
                node_id,
                token=TOKEN,
                command_id=commands[0].id,
                lease_token="forged",
                success=True,
                result={},
            )


async def test_auto_upgrade_enqueues_when_version_differs(app_state: AppState):
    node_id, _ = await _seed(app_state)
    async with app_state.db.session() as session:
        command = await _svc(app_state, session).ensure_upgrade(node_id, target_version="2.0.0")
    assert command is not None
    assert command.kind.value == "upgrade"
    assert command.payload["target_version"] == "2.0.0"


async def test_auto_upgrade_noop_when_current(app_state: AppState):
    node_id, _ = await _seed(app_state)
    async with app_state.db.session() as session:
        node = await session.get(Node, node_id)
        meta = dict(node.node_metadata)
        meta["reported_state"] = {"agent_version": "2.0.0"}
        node.node_metadata = meta
        await session.flush()
    async with app_state.db.session() as session:
        command = await _svc(app_state, session).ensure_upgrade(node_id, target_version="2.0.0")
    assert command is None


async def test_provider_health_persists_and_aggregates(app_state: AppState):
    node_id, _ = await _seed(app_state)
    checks = [
        {"provider_name": "xray", "status": "healthy", "latency_ms": 5.0, "detail": None},
        {"provider_name": "sing-box", "status": "degraded", "latency_ms": 80.0, "detail": "slow"},
    ]
    async with app_state.db.session() as session:
        count = await _svc(app_state, session).record_provider_health(
            node_id, token=TOKEN, checks=checks
        )
    assert count == 2
    async with app_state.db.session() as session:
        latest = await _svc(app_state, session).provider_health(node_id)
    statuses = {r.provider_name: r.status for r in latest}
    assert statuses["xray"] is ProviderHealthStatus.HEALTHY
    assert statuses["sing-box"] is ProviderHealthStatus.DEGRADED


async def test_metrics_stream_bounded(app_state: AppState):
    node_id, _ = await _seed(app_state)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    samples = [
        {"name": "cpu", "value": float(i), "observed_at": (base + timedelta(seconds=i)).isoformat()}
        for i in range(20)
    ]
    async with app_state.db.session() as session:
        accepted, _ = await _svc(app_state, session).push_metrics(
            node_id, token=TOKEN, samples=samples
        )
    assert accepted == 20
    async with app_state.db.session() as session:
        read = await _svc(app_state, session).read_metrics(node_id, limit=5)
    assert len(read) == 5


async def test_log_stream_roundtrip(app_state: AppState):
    node_id, _ = await _seed(app_state)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    lines = [
        {
            "level": "info",
            "message": f"line {i}",
            "observed_at": (base + timedelta(seconds=i)).isoformat(),
        }
        for i in range(5)
    ]
    async with app_state.db.session() as session:
        accepted, dropped = await _svc(app_state, session).push_logs(
            node_id, token=TOKEN, lines=lines
        )
    assert accepted == 5
    assert dropped == 0
    async with app_state.db.session() as session:
        read = await _svc(app_state, session).read_logs(node_id, limit=10)
    assert len(read) == 5


async def test_reconcile_once_detects_and_heals(app_state: AppState):
    from app.agent.reconcile import reconcile_once

    node_id, _ = await _seed(app_state, active_assignments=2)
    stats = await reconcile_once(
        app_state.db,
        signer=_signer(),
        events=app_state.events,
        self_healing_enabled=True,
        target_version="3.0.0",
    )
    assert stats["drifted"] >= 1
    assert stats["healed"] >= 1
    assert stats["upgrades"] >= 1
    async with app_state.db.session() as session:
        _, commands = await _svc(app_state, session).lease_commands(node_id, token=TOKEN)
    kinds = {c.kind.value for c in commands}
    assert "apply_config" in kinds
    assert "upgrade" in kinds
