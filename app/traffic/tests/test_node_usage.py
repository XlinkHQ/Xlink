from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.providers.base.models import ProviderKind
from app.traffic.schemas import TrafficBatch, TrafficSample
from app.traffic.service import TrafficService

BASE = datetime(2026, 1, 1, tzinfo=UTC)


async def _seed_node(
    app_state: AppState,
    *,
    usage_coefficient: float = 1.0,
    user_count: int = 1,
) -> dict:
    ids: dict = {"assignments": [], "users": []}
    async with app_state.db.session() as session:
        node = Node(
            name=f"n-{uuid.uuid4().hex[:8]}",
            slug=f"n-{uuid.uuid4().hex[:8]}",
            host="10.0.0.1",
            port=443,
            max_users=100,
            usage_coefficient=usage_coefficient,
            node_metadata={},
            status=NodeStatus.ACTIVE,
        )
        session.add(node)
        await session.flush()
        ids["node_id"] = node.id
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
        for _ in range(user_count):
            user = User(
                email=f"u-{uuid.uuid4().hex[:8]}@x.io",
                username=f"u-{uuid.uuid4().hex[:8]}",
                hashed_password=hash_password("strong-password-1234-AB!"),
                role=UserRole.USER,
            )
            session.add(user)
            await session.flush()
            ids["users"].append(user.id)
            assignment = ClientAssignment(
                user_id=user.id,
                profile_id=profile.id,
                node_id=node.id,
                provider_kind=ProviderKind.XRAY,
                status=AssignmentStatus.ACTIVE,
            )
            session.add(assignment)
            await session.flush()
            ids["assignments"].append(assignment.id)
    return ids


def _batch(node_id, assignment_id, *, count=3, batch_id="b1", start=BASE):
    samples = tuple(
        TrafficSample(
            assignment_id=assignment_id,
            upload_bytes=100,
            download_bytes=200,
            collected_at=start + timedelta(minutes=i),
        )
        for i in range(count)
    )
    return TrafficBatch(node_id=node_id, batch_id=batch_id, samples=samples)


async def _used_bytes(app_state: AppState, assignment_id: uuid.UUID) -> int:
    async with app_state.db.session() as session:
        return int((await session.get(ClientAssignment, assignment_id)).used_bytes)


async def test_coefficient_one_is_neutral(app_state: AppState):
    ids = await _seed_node(app_state, usage_coefficient=1.0)
    aid = ids["assignments"][0]
    async with app_state.db.session() as session:
        await TrafficService(session).ingest(_batch(ids["node_id"], aid, count=3))

    assert await _used_bytes(app_state, aid) == 900


async def test_coefficient_scales_quota(app_state: AppState):
    ids = await _seed_node(app_state, usage_coefficient=2.5)
    aid = ids["assignments"][0]
    async with app_state.db.session() as session:
        await TrafficService(session).ingest(_batch(ids["node_id"], aid, count=3))

    assert await _used_bytes(app_state, aid) == 2250


async def test_coefficient_leaves_raw_records_unscaled(app_state: AppState):
    ids = await _seed_node(app_state, usage_coefficient=2.5)
    aid = ids["assignments"][0]
    async with app_state.db.session() as session:
        service = TrafficService(session)
        await service.ingest(_batch(ids["node_id"], aid, count=3))
    async with app_state.db.session() as session:
        usage = await TrafficService(session).usage_for_assignment(aid)

    assert usage.total_bytes == 900


async def test_usage_by_node_rollup(app_state: AppState):
    ids = await _seed_node(app_state, user_count=2)
    async with app_state.db.session() as session:
        service = TrafficService(session)
        await service.ingest(_batch(ids["node_id"], ids["assignments"][0], count=2, batch_id="a"))
        await service.ingest(_batch(ids["node_id"], ids["assignments"][1], count=3, batch_id="b"))
    async with app_state.db.session() as session:
        by_node = await TrafficService(session).usage_by_node()

    assert by_node[ids["node_id"]] == 1500


async def test_usage_by_node_user_breakdown(app_state: AppState):
    ids = await _seed_node(app_state, user_count=2)
    async with app_state.db.session() as session:
        service = TrafficService(session)
        await service.ingest(_batch(ids["node_id"], ids["assignments"][0], count=2, batch_id="a"))
        await service.ingest(_batch(ids["node_id"], ids["assignments"][1], count=4, batch_id="b"))
    async with app_state.db.session() as session:
        rows = await TrafficService(session).usage_by_node_user(ids["node_id"])
    by_user = dict(rows)
    assert by_user[ids["users"][0]] == 600
    assert by_user[ids["users"][1]] == 1200

    assert rows[0][0] == ids["users"][1]


async def test_usage_by_user_node(app_state: AppState):
    ids = await _seed_node(app_state, user_count=1)
    async with app_state.db.session() as session:
        await TrafficService(session).ingest(
            _batch(ids["node_id"], ids["assignments"][0], count=3, batch_id="un")
        )
    async with app_state.db.session() as session:
        rows = await TrafficService(session).usage_by_user_node(ids["users"][0])

    assert len(rows) == 1
    node_id, node_name, total = rows[0]
    assert node_id == ids["node_id"]
    assert total == 900
    assert isinstance(node_name, str) and node_name


async def test_usage_hourly_for_node(app_state: AppState):
    ids = await _seed_node(app_state, user_count=1)
    async with app_state.db.session() as session:
        await TrafficService(session).ingest(
            _batch(ids["node_id"], ids["assignments"][0], count=3, batch_id="hr")
        )
    async with app_state.db.session() as session:
        rows = await TrafficService(session).usage_hourly_for_node(ids["node_id"], hours=24 * 400)
    assert sum(up + dn for _, up, dn in rows) == 900
    assert all(isinstance(ts, str) for ts, _, _ in rows)
