from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.agent.heartbeat import hash_agent_token
from app.agent.models import RetryPolicy
from app.agent.service import NodeAgentService
from app.core.exceptions import AuthenticationError
from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.providers.base.models import ProviderKind
from app.traffic.repository import TrafficRepository
from app.traffic.schemas import TrafficBatch, TrafficSample

TOKEN = "agent-token-xyz"
BASE = datetime(2026, 1, 1, tzinfo=UTC)


async def _seed(app_state: AppState) -> tuple[uuid.UUID, uuid.UUID]:
    async with app_state.db.session() as session:
        node = Node(
            name=f"n-{uuid.uuid4().hex[:8]}",
            slug=f"n-{uuid.uuid4().hex[:8]}",
            host="203.0.113.5",
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
        return node.id, assignment.id


def _batch(node_id, assignment_id, *, count=3, batch_id="b1"):
    return TrafficBatch(
        node_id=node_id,
        batch_id=batch_id,
        samples=tuple(
            TrafficSample(
                assignment_id=assignment_id,
                upload_bytes=10,
                download_bytes=20,
                collected_at=BASE + timedelta(minutes=i),
            )
            for i in range(count)
        ),
    )


async def test_traffic_sync_persists(app_state: AppState):
    node_id, assignment_id = await _seed(app_state)
    async with app_state.db.session() as session:
        service = NodeAgentService(session)
        result = await service.report_traffic(
            node_id, token=TOKEN, batch=_batch(node_id, assignment_id, count=3)
        )
    assert result.inserted == 3
    async with app_state.db.session() as session:
        assert await TrafficRepository(session).count() == 3


async def test_traffic_sync_bad_token(app_state: AppState):
    node_id, assignment_id = await _seed(app_state)
    async with app_state.db.session() as session:
        service = NodeAgentService(session)
        with pytest.raises(AuthenticationError):
            await service.report_traffic(
                node_id, token="wrong", batch=_batch(node_id, assignment_id)
            )


async def test_duplicate_batch_idempotent(app_state: AppState):
    node_id, assignment_id = await _seed(app_state)
    batch = _batch(node_id, assignment_id, count=3, batch_id="same")
    async with app_state.db.session() as session:
        first = await NodeAgentService(session).report_traffic(node_id, token=TOKEN, batch=batch)
    async with app_state.db.session() as session:
        second = await NodeAgentService(session).report_traffic(node_id, token=TOKEN, batch=batch)
    assert first.inserted == 3
    assert second.inserted == 0
    assert second.duplicates == 3
    async with app_state.db.session() as session:
        assert await TrafficRepository(session).count() == 3


async def test_malformed_payload_rejected():
    with pytest.raises(ValueError):
        TrafficSample(
            assignment_id=uuid.uuid4(),
            upload_bytes=-1,
            download_bytes=10,
            collected_at=BASE,
        )


async def test_oversized_batch_rejected():
    node_id = uuid.uuid4()
    aid = uuid.uuid4()
    samples = tuple(
        TrafficSample(
            assignment_id=aid,
            upload_bytes=1,
            download_bytes=1,
            collected_at=BASE + timedelta(seconds=i),
        )
        for i in range(10001)
    )
    with pytest.raises(ValueError):
        TrafficBatch(node_id=node_id, batch_id="too-big", samples=samples)


async def test_retry_support_succeeds_after_transient(app_state: AppState):
    node_id, assignment_id = await _seed(app_state)
    async with app_state.db.session() as session:
        service = NodeAgentService(
            session, retry=RetryPolicy(max_attempts=3, base_delay_seconds=0.0)
        )
        attempts = {"n": 0}

        async def flaky():
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise ConnectionError("transient")
            return await service.report_traffic(
                node_id, token=TOKEN, batch=_batch(node_id, assignment_id, count=2)
            )

        result = await service.with_retry(flaky)
    assert result.inserted == 2
    assert attempts["n"] == 2
