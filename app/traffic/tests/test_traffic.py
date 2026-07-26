from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

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
from app.traffic.collector import TrafficCollector
from app.traffic.repository import TrafficRepository
from app.traffic.retention import TrafficRetention
from app.traffic.schemas import TrafficBatch, TrafficSample
from app.traffic.service import TrafficService

BASE = datetime(2026, 1, 1, tzinfo=UTC)


async def _seed(app_state: AppState, *, traffic_limit: int | None = None) -> dict:
    ids: dict = {}
    async with app_state.db.session() as session:
        user = User(
            email=f"u-{uuid.uuid4().hex[:8]}@x.io",
            username=f"u-{uuid.uuid4().hex[:8]}",
            hashed_password=hash_password("strong-password-1234-AB!"),
            role=UserRole.USER,
        )
        session.add(user)
        await session.flush()
        ids["user_id"] = user.id
        node = Node(
            name=f"n-{uuid.uuid4().hex[:8]}",
            slug=f"n-{uuid.uuid4().hex[:8]}",
            host="10.0.0.1",
            port=443,
            max_users=100,
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
        assignment = ClientAssignment(
            user_id=user.id,
            profile_id=profile.id,
            node_id=node.id,
            provider_kind=ProviderKind.XRAY,
            status=AssignmentStatus.ACTIVE,
            traffic_limit_bytes=traffic_limit,
        )
        session.add(assignment)
        await session.flush()
        ids["assignment_id"] = assignment.id
    return ids


def _batch(node_id, assignment_id, *, count=3, batch_id="b1", start=BASE):
    samples = tuple(
        TrafficSample(
            assignment_id=assignment_id,
            upload_bytes=100 + i,
            download_bytes=200 + i,
            collected_at=start + timedelta(minutes=i),
        )
        for i in range(count)
    )
    return TrafficBatch(node_id=node_id, batch_id=batch_id, samples=samples)


async def test_ingestion_inserts_rows(app_state: AppState):
    ids = await _seed(app_state)
    async with app_state.db.session() as session:
        service = TrafficService(session)
        result = await service.ingest(_batch(ids["node_id"], ids["assignment_id"], count=3))
    assert result.received == 3
    assert result.inserted == 3
    assert result.duplicates == 0


async def test_aggregation_correctness(app_state: AppState):
    ids = await _seed(app_state)
    async with app_state.db.session() as session:
        service = TrafficService(session)
        await service.ingest(_batch(ids["node_id"], ids["assignment_id"], count=3))
    async with app_state.db.session() as session:
        repo = TrafficRepository(session)
        usage = await repo.usage_for_assignment(ids["assignment_id"])
        totals = await repo.totals()
    assert usage.sample_count == 3
    assert usage.upload_bytes == 100 + 101 + 102
    assert usage.download_bytes == 200 + 201 + 202
    assert usage.total_bytes == usage.upload_bytes + usage.download_bytes
    assert totals.total_bytes == usage.total_bytes
    assert totals.record_count == 3


async def test_duplicate_prevention_same_batch(app_state: AppState):
    ids = await _seed(app_state)
    dup = TrafficSample(
        assignment_id=ids["assignment_id"],
        upload_bytes=10,
        download_bytes=20,
        collected_at=BASE,
    )
    batch = TrafficBatch(node_id=ids["node_id"], batch_id="dup", samples=(dup, dup, dup))
    async with app_state.db.session() as session:
        result = await TrafficService(session).ingest(batch)
    assert result.inserted == 1
    assert result.duplicates == 2


async def test_duplicate_prevention_replayed_batch(app_state: AppState):
    ids = await _seed(app_state)
    batch = _batch(ids["node_id"], ids["assignment_id"], count=3, batch_id="b1")
    async with app_state.db.session() as session:
        first = await TrafficService(session).ingest(batch)
    async with app_state.db.session() as session:
        second = await TrafficService(session).ingest(batch)
    assert first.inserted == 3
    assert second.inserted == 0
    assert second.duplicates == 3
    async with app_state.db.session() as session:
        assert await TrafficRepository(session).count() == 3


async def test_bulk_insert_repository(app_state: AppState):
    ids = await _seed(app_state)
    rows = [
        {
            "assignment_id": ids["assignment_id"],
            "node_id": ids["node_id"],
            "upload_bytes": i,
            "download_bytes": i,
            "total_bytes": 2 * i,
            "collected_at": BASE + timedelta(seconds=i),
        }
        for i in range(500)
    ]
    async with app_state.db.session() as session:
        deltas, inserted = await TrafficRepository(session).bulk_insert(rows)
    assert inserted == 500
    assert deltas[ids["assignment_id"]] == sum(2 * i for i in range(500))
    async with app_state.db.session() as session:
        assert await TrafficRepository(session).count() == 500


async def test_high_volume_ingest(app_state: AppState):
    ids = await _seed(app_state)
    big = TrafficBatch(
        node_id=ids["node_id"],
        batch_id="big",
        samples=tuple(
            TrafficSample(
                assignment_id=ids["assignment_id"],
                upload_bytes=1,
                download_bytes=1,
                collected_at=BASE + timedelta(seconds=i),
            )
            for i in range(5000)
        ),
    )
    async with app_state.db.session() as session:
        result = await TrafficService(session).ingest(big)
    assert result.inserted == 5000
    async with app_state.db.session() as session:
        totals = await TrafficRepository(session).totals()
    assert totals.record_count == 5000
    assert totals.total_bytes == 5000 * 2


async def test_retention_cleanup(app_state: AppState):
    ids = await _seed(app_state)
    now = datetime(2026, 6, 1, tzinfo=UTC)
    old = TrafficSample(
        assignment_id=ids["assignment_id"],
        upload_bytes=1,
        download_bytes=1,
        collected_at=now - timedelta(days=120),
    )
    fresh = TrafficSample(
        assignment_id=ids["assignment_id"],
        upload_bytes=1,
        download_bytes=1,
        collected_at=now - timedelta(days=1),
    )
    batch = TrafficBatch(node_id=ids["node_id"], batch_id="ret", samples=(old, fresh))
    async with app_state.db.session() as session:
        await TrafficService(session).ingest(batch)
    async with app_state.db.session() as session:
        deleted = await TrafficRetention(session, retention_days=90).purge(now=now)
    assert deleted == 1
    async with app_state.db.session() as session:
        assert await TrafficRepository(session).count() == 1


async def test_foreign_node_samples_skipped(app_state: AppState):
    ids = await _seed(app_state)
    other_assignment = uuid.uuid4()
    batch = TrafficBatch(
        node_id=ids["node_id"],
        batch_id="mixed",
        samples=(
            TrafficSample(
                assignment_id=ids["assignment_id"],
                upload_bytes=1,
                download_bytes=1,
                collected_at=BASE,
            ),
            TrafficSample(
                assignment_id=other_assignment,
                upload_bytes=9,
                download_bytes=9,
                collected_at=BASE,
            ),
        ),
    )
    async with app_state.db.session() as session:
        result = await TrafficService(session).ingest(batch)
    assert result.inserted == 1
    assert result.skipped == 1


async def test_traffic_limit_event_emitted(app_state: AppState):
    ids = await _seed(app_state, traffic_limit=500)
    captured: list[TrafficLimitReached] = []

    async def handler(event: TrafficLimitReached) -> None:
        captured.append(event)

    registry = EventRegistry()
    registry.subscribe(TrafficLimitReached, handler)
    bus = EventBus(registry)
    batch = TrafficBatch(
        node_id=ids["node_id"],
        batch_id="limit",
        samples=(
            TrafficSample(
                assignment_id=ids["assignment_id"],
                upload_bytes=400,
                download_bytes=400,
                collected_at=BASE,
            ),
        ),
    )
    async with app_state.db.session() as session:
        await TrafficService(session, events=bus).ingest(batch)
    assert len(captured) == 1
    assert captured[0].used_bytes == 800
    assert captured[0].limit_bytes == 500


def test_collector_dedup_and_validation():
    collector = TrafficCollector()
    node_id = uuid.uuid4()
    aid = uuid.uuid4()
    s = TrafficSample(assignment_id=aid, upload_bytes=1, download_bytes=2, collected_at=BASE)
    batch = TrafficBatch(node_id=node_id, batch_id="c", samples=(s, s))
    prepared = collector.prepare(batch)
    assert prepared.received == 2
    assert len(prepared.rows) == 1
    assert prepared.deduped == 1


async def test_online_user_ids_recent(app_state: AppState):
    ids = await _seed(app_state)
    now = datetime.now(UTC)
    async with app_state.db.session() as session:
        service = TrafficService(session)

        await service.ingest(
            _batch(ids["node_id"], ids["assignment_id"], count=1, start=now - timedelta(seconds=30))
        )
    async with app_state.db.session() as session:
        online = await TrafficService(session).online_user_ids(window_seconds=180)
    assert ids["user_id"] in online


async def test_online_user_ids_stale_excluded(app_state: AppState):
    ids = await _seed(app_state)
    async with app_state.db.session() as session:
        service = TrafficService(session)

        await service.ingest(_batch(ids["node_id"], ids["assignment_id"], count=1))
    async with app_state.db.session() as session:
        online = await TrafficService(session).online_user_ids(window_seconds=180)
    assert ids["user_id"] not in online
