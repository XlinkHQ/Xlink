from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import event

from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.events.bus import EventBus
from app.events.models import TrafficLimitReached
from app.events.registry import EventRegistry
from app.providers.base.models import ProviderKind
from app.traffic.repository import TrafficRepository
from app.traffic.schemas import TrafficBatch, TrafficSample
from app.traffic.service import TrafficService

BASE = datetime(2026, 1, 1, tzinfo=UTC)


async def _seed(app_state: AppState, *, count: int, limit: int | None = None) -> tuple:
    async with app_state.db.session() as session:
        user = User(
            email=f"u-{uuid.uuid4().hex[:8]}@x.io",
            username=f"u-{uuid.uuid4().hex[:8]}",
            hashed_password=hash_password("strong-password-1234"),
            role=UserRole.USER,
        )
        session.add(user)
        await session.flush()
        node = Node(
            name="n",
            slug=f"n-{uuid.uuid4().hex[:8]}",
            host="10.0.0.1",
            port=443,
            max_users=100000,
            node_metadata={},
            status=NodeStatus.ACTIVE,
        )
        session.add(node)
        await session.flush()
        assignment_ids = []
        for _i in range(count):
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
                traffic_limit_bytes=limit,
            )
            session.add(assignment)
            await session.flush()
            assignment_ids.append(assignment.id)
        return node.id, user.id, assignment_ids


async def test_thousand_assignment_batch_no_sum_queries(app_state: AppState):
    node_id, _, aids = await _seed(app_state, count=1000)
    samples = tuple(
        TrafficSample(
            assignment_id=aid,
            upload_bytes=500,
            download_bytes=500,
            collected_at=BASE,
        )
        for aid in aids
    )
    batch = TrafficBatch(node_id=node_id, batch_id="big", samples=samples)

    sum_queries = {"n": 0}

    def _count(conn, cursor, statement, *args):
        text = statement.lower()
        if "sum(" in text and "traffic_records" in text:
            sum_queries["n"] += 1

    engine = app_state.db.engine.sync_engine
    event.listen(engine, "before_cursor_execute", _count)
    try:
        async with app_state.db.session() as session:
            result = await TrafficService(session).ingest(batch)
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert result.inserted == 1000
    assert sum_queries["n"] == 0


async def test_used_bytes_incremented_in_one_update(app_state: AppState):
    node_id, _, aids = await _seed(app_state, count=1000)
    samples = tuple(
        TrafficSample(assignment_id=aid, upload_bytes=300, download_bytes=200, collected_at=BASE)
        for aid in aids
    )
    batch = TrafficBatch(node_id=node_id, batch_id="b", samples=samples)
    async with app_state.db.session() as session:
        await TrafficService(session).ingest(batch)
    async with app_state.db.session() as session:
        a0 = await session.get(ClientAssignment, aids[0])
        a_last = await session.get(ClientAssignment, aids[-1])
        assert a0.used_bytes == 500
        assert a_last.used_bytes == 500


async def test_limit_event_uses_used_bytes_not_sum(app_state: AppState):
    node_id, _user_id, aids = await _seed(app_state, count=10, limit=500)
    captured: list[TrafficLimitReached] = []

    async def handler(event_):
        captured.append(event_)

    registry = EventRegistry()
    registry.subscribe(TrafficLimitReached, handler)
    bus = EventBus(registry)
    samples = tuple(
        TrafficSample(assignment_id=aid, upload_bytes=400, download_bytes=400, collected_at=BASE)
        for aid in aids
    )
    batch = TrafficBatch(node_id=node_id, batch_id="lim", samples=samples)
    async with app_state.db.session() as session:
        await TrafficService(session, events=bus).ingest(batch)
    assert len(captured) == 10
    assert captured[0].used_bytes == 800


async def test_used_bytes_accumulates_across_batches(app_state: AppState):
    node_id, _, aids = await _seed(app_state, count=1)
    aid = aids[0]
    for i in range(3):
        async with app_state.db.session() as session:
            batch = TrafficBatch(
                node_id=node_id,
                batch_id=f"b{i}",
                samples=(
                    TrafficSample(
                        assignment_id=aid,
                        upload_bytes=100,
                        download_bytes=100,
                        collected_at=BASE + timedelta(minutes=i),
                    ),
                ),
            )
            await TrafficService(session).ingest(batch)
    async with app_state.db.session() as session:
        assignment = await session.get(ClientAssignment, aid)
        assert assignment.used_bytes == 600
        repo_usage = await TrafficRepository(session).usage_for_assignment(aid)
        assert repo_usage.total_bytes == 600
