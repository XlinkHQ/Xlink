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

TOKEN = "agent-endpoint-token"


async def _seed(app_state: AppState) -> tuple[uuid.UUID, uuid.UUID]:
    async with app_state.db.session() as session:
        node = Node(
            name="n",
            slug=f"n-{uuid.uuid4().hex[:8]}",
            host="203.0.113.9",
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
        return node.id, assignment.id


def _payload(assignment_id: uuid.UUID) -> dict:
    return {
        "batch_id": "http-1",
        "samples": [
            {
                "assignment_id": str(assignment_id),
                "upload_bytes": 100,
                "download_bytes": 200,
                "collected_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            }
        ],
    }


async def test_report_traffic_endpoint_success(client: AsyncClient, app_state: AppState):
    node_id, assignment_id = await _seed(app_state)
    resp = await client.post(
        f"/api/v1/agent/nodes/{node_id}/traffic",
        json=_payload(assignment_id),
        headers={"X-Agent-Token": TOKEN},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["inserted"] == 1
    assert body["received"] == 1


async def test_report_traffic_endpoint_bad_token(client: AsyncClient, app_state: AppState):
    node_id, assignment_id = await _seed(app_state)
    resp = await client.post(
        f"/api/v1/agent/nodes/{node_id}/traffic",
        json=_payload(assignment_id),
        headers={"X-Agent-Token": "wrong"},
    )
    assert resp.status_code == 401


async def test_report_traffic_endpoint_missing_token(client: AsyncClient, app_state: AppState):
    node_id, assignment_id = await _seed(app_state)
    resp = await client.post(
        f"/api/v1/agent/nodes/{node_id}/traffic",
        json=_payload(assignment_id),
    )
    assert resp.status_code == 422


async def test_report_traffic_endpoint_malformed(client: AsyncClient, app_state: AppState):
    node_id, _ = await _seed(app_state)
    resp = await client.post(
        f"/api/v1/agent/nodes/{node_id}/traffic",
        json={"batch_id": "x", "samples": [{"assignment_id": "not-a-uuid"}]},
        headers={"X-Agent-Token": TOKEN},
    )
    assert resp.status_code == 422
