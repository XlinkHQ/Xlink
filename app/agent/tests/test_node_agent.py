from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.agent.heartbeat import hash_agent_token
from app.agent.models import AgentHeartbeat, NodeStats, RetryPolicy, SyncCursor
from app.agent.scheduler import NodeAgentScheduler
from app.agent.service import NodeAgentService
from app.core.exceptions import AuthenticationError
from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.events.models import NodeOffline
from app.providers.base.models import ProviderKind

TOKEN = "node-token-123"


async def _seed_node(app_state: AppState, *, status: NodeStatus = NodeStatus.OFFLINE) -> uuid.UUID:
    async with app_state.db.session() as session:
        node = Node(
            name=f"node-{uuid.uuid4().hex[:8]}",
            slug=f"node-{uuid.uuid4().hex[:8]}",
            host="203.0.113.20",
            port=443,
            max_users=100,
            current_users=0,
            status=status,
            node_metadata={"agent_token_hash": hash_agent_token(TOKEN)},
        )
        session.add(node)
        await session.flush()
        return node.id


async def _seed_assignments(app_state: AppState, node_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    async with app_state.db.session() as session:
        user = User(
            email=f"agent-{uuid.uuid4().hex[:8]}@example.com",
            username=f"agent{uuid.uuid4().hex[:8]}",
            hashed_password=hash_password("strong-password-123456"),
            role=UserRole.USER,
        )
        session.add(user)
        await session.flush()
        ids: list[uuid.UUID] = []
        for index in range(2):
            profile = Profile(
                name=f"profile-{uuid.uuid4().hex[:8]}",
                slug=f"profile-{uuid.uuid4().hex[:8]}",
                provider_kind=ProviderKind.XRAY,
                node_id=node_id,
                protocol="vless",
                settings={"flow": "vision"},
                is_active=True,
            )
            session.add(profile)
            await session.flush()
            assignment = ClientAssignment(
                user_id=user.id,
                profile_id=profile.id,
                node_id=node_id,
                provider_kind=ProviderKind.XRAY,
                provider_client_id=str(uuid.uuid4()),
                status=AssignmentStatus.ACTIVE,
                updated_at=base + timedelta(minutes=index),
            )
            session.add(assignment)
            await session.flush()
            ids.append(assignment.id)
        return ids[0], ids[1]


async def _agent(app_state: AppState) -> NodeAgentService:
    return NodeAgentService(app_state.db.sessionmaker(), events=app_state.events)


async def test_heartbeat_updates_node_status_and_stats(app_state: AppState) -> None:
    node_id = await _seed_node(app_state)
    agent = await _agent(app_state)

    node = await agent.heartbeat(
        AgentHeartbeat(
            node_id=node_id,
            stats=NodeStats(current_users=7, cpu_percent=12.5, rx_bytes=100),
        ),
        token=TOKEN,
    )

    assert node.status is NodeStatus.ACTIVE
    # current_users is DB-authoritative (COUNT of ACTIVE assignments); the
    # agent-reported count is telemetry only, kept in metadata.
    assert node.current_users == 0
    assert node.node_metadata["agent_reported_users"] == 7
    assert node.last_seen_at is not None
    assert node.node_metadata["agent_stats"]["cpu_percent"] == 12.5


async def test_health_check_requires_valid_node_token(app_state: AppState) -> None:
    node_id = await _seed_node(app_state, status=NodeStatus.ACTIVE)
    agent = await _agent(app_state)

    assert await agent.health_check(node_id, token=TOKEN) is True
    with pytest.raises(AuthenticationError):
        await agent.health_check(node_id, token="wrong")


async def test_assignment_sync_is_incremental(app_state: AppState) -> None:
    node_id = await _seed_node(app_state, status=NodeStatus.ACTIVE)
    first_id, second_id = await _seed_assignments(app_state, node_id)
    agent = await _agent(app_state)

    first_batch = await agent.assignment_sync(node_id, token=TOKEN, limit=1)
    assert first_batch.has_more is True
    assert [item.assignment_id for item in first_batch.items] == [first_id]

    assert first_batch.next_cursor is not None
    second_batch = await agent.assignment_sync(
        node_id,
        token=TOKEN,
        cursor=SyncCursor(
            updated_at=first_batch.next_cursor.updated_at,
            assignment_id=first_batch.next_cursor.assignment_id,
        ),
        limit=10,
    )

    assert second_batch.has_more is False
    assert [item.assignment_id for item in second_batch.items] == [second_id]
    assert second_batch.items[0].settings["protocol"] == "vless"


async def test_retry_support(app_state: AppState) -> None:
    attempts = 0
    service = NodeAgentService(
        app_state.db.sessionmaker(),
        retry=RetryPolicy(max_attempts=3, base_delay_seconds=0.0),
    )

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("not yet")
        return "ok"

    assert await service.with_retry(flaky) == "ok"
    assert attempts == 3


async def test_node_offline_detection_publishes_event(app_state: AppState) -> None:
    seen: list[NodeOffline] = []

    async def handler(event):
        seen.append(event)

    app_state.events.subscribe(NodeOffline, handler)
    node_id = await _seed_node(app_state, status=NodeStatus.ACTIVE)
    async with app_state.db.session() as session:
        node = await session.get(Node, node_id)
        assert node is not None
        node.last_seen_at = datetime.now(UTC) - timedelta(minutes=10)

    scheduler = NodeAgentScheduler(
        app_state.db,
        events=app_state.events,
        interval_seconds=999,
        offline_after_seconds=60,
    )
    marked = await scheduler.detect_offline_once()

    assert marked == 1
    assert seen and seen[0].node_id == node_id
    async with app_state.db.session() as session:
        node = await session.get(Node, node_id)
        assert node is not None
        assert node.status is NodeStatus.OFFLINE
