from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import AsyncClient

from app.agent.heartbeat import hash_agent_token
from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.providers.base.models import ProviderKind

TOKEN = "agent-endpoint-token-adv"
LOGIN = "/api/v1/auth/login"
ADMIN_PW = "admin-strong-password-1234"


async def _seed(app_state: AppState) -> uuid.UUID:
    async with app_state.db.session() as session:
        admin = User(
            email="admin@x.io",
            username="admin",
            hashed_password=hash_password(ADMIN_PW),
            role=UserRole.ADMIN,
        )
        session.add(admin)
        node = Node(
            name="n",
            slug=f"n-{uuid.uuid4().hex[:8]}",
            host="203.0.113.8",
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
        return node.id


async def _admin_headers(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(LOGIN, json={"identifier": "admin", "password": ADMIN_PW})
    token = resp.json()["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _agent(node_id: uuid.UUID) -> str:
    return f"/api/v1/agent/nodes/{node_id}"


async def test_pull_config_endpoint(client: AsyncClient, app_state: AppState):
    node_id = await _seed(app_state)
    resp = await client.get(_agent(node_id) + "/config", headers={"X-Agent-Token": TOKEN})
    assert resp.status_code == 200
    body = resp.json()
    assert body["assignment_count"] == 1
    assert len(body["config_version"]) == 32


async def test_report_state_endpoint(client: AsyncClient, app_state: AppState):
    node_id = await _seed(app_state)
    resp = await client.post(
        _agent(node_id) + "/state",
        json={
            "config_version": "stale",
            "agent_version": "1.0",
            "applied": {},
            "provider_status": {},
        },
        headers={"X-Agent-Token": TOKEN},
    )
    assert resp.status_code == 200
    assert resp.json()["severity"] in ("low", "medium", "high")


async def test_enqueue_and_lease_command(client: AsyncClient, app_state: AppState):
    node_id = await _seed(app_state)
    admin = await _admin_headers(client)
    enq = await client.post(
        _agent(node_id) + "/commands",
        json={"kind": "reload", "payload": {}, "origin": "operator"},
        headers=admin,
    )
    assert enq.status_code == 201
    assert enq.json()["kind"] == "reload"
    lease = await client.post(_agent(node_id) + "/commands/lease", headers={"X-Agent-Token": TOKEN})
    assert lease.status_code == 200
    body = lease.json()
    assert len(body["commands"]) == 1
    assert body["lease_token"]
    result = await client.post(
        _agent(node_id) + "/commands/result",
        json={
            "command_id": body["commands"][0]["command_id"],
            "lease_token": body["lease_token"],
            "success": True,
            "result": {"done": True},
        },
        headers={"X-Agent-Token": TOKEN},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "succeeded"


async def test_enqueue_command_requires_admin(client: AsyncClient, app_state: AppState):
    node_id = await _seed(app_state)
    resp = await client.post(
        _agent(node_id) + "/commands",
        json={"kind": "reload", "payload": {}},
        headers={"X-Agent-Token": TOKEN},
    )
    assert resp.status_code in (401, 403)


async def test_enqueue_disallowed_kind(client: AsyncClient, app_state: AppState):
    node_id = await _seed(app_state)
    admin = await _admin_headers(client)
    resp = await client.post(
        _agent(node_id) + "/commands",
        json={"kind": "exec_shell", "payload": {}},
        headers=admin,
    )
    assert resp.status_code == 422


async def test_provider_health_endpoint(client: AsyncClient, app_state: AppState):
    node_id = await _seed(app_state)
    resp = await client.post(
        _agent(node_id) + "/provider-health",
        json={"checks": [{"provider_name": "xray", "status": "healthy", "latency_ms": 3.0}]},
        headers={"X-Agent-Token": TOKEN},
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1


async def test_metrics_and_logs_stream_endpoint(client: AsyncClient, app_state: AppState):
    node_id = await _seed(app_state)
    now = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    m = await client.post(
        _agent(node_id) + "/metrics",
        json={"samples": [{"name": "cpu", "value": 0.5, "observed_at": now}]},
        headers={"X-Agent-Token": TOKEN},
    )
    assert m.status_code == 200
    assert m.json()["accepted"] == 1
    log = await client.post(
        _agent(node_id) + "/logs",
        json={"lines": [{"level": "info", "message": "hello", "observed_at": now}]},
        headers={"X-Agent-Token": TOKEN},
    )
    assert log.status_code == 200
    assert log.json()["accepted"] == 1


async def test_agent_endpoints_reject_bad_token(client: AsyncClient, app_state: AppState):
    node_id = await _seed(app_state)
    resp = await client.get(_agent(node_id) + "/config", headers={"X-Agent-Token": "nope"})
    assert resp.status_code == 401
