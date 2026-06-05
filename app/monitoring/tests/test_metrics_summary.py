from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import fakeredis.aioredis
import pytest

from app.core.security import hash_password
from app.db.redis import RedisCache
from app.db.session import Database
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.monitoring.service import MonitoringService
from app.monitoring.summary import MetricsSummaryCache, refresh_summary
from app.providers.base.models import ProviderKind
from app.providers.discovery import build_registry
from app.traffic.repository import TrafficRepository
from app.traffic.schemas import TrafficBatch, TrafficSample
from app.traffic.service import TrafficService


@pytest.fixture
async def cache() -> AsyncIterator[RedisCache]:
    c = RedisCache.__new__(RedisCache)
    c._settings = None
    c._client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    c._pool = None
    try:
        yield c
    finally:
        await c.client.aclose()


async def _seed(db: Database) -> uuid.UUID:
    async with db.session() as session:
        user = User(
            email=f"u{uuid.uuid4().hex[:6]}@x.io",
            username=f"u{uuid.uuid4().hex[:6]}",
            hashed_password=hash_password("strong-password-123456"),
            role=UserRole.USER,
        )
        session.add(user)
        await session.flush()
        node = Node(
            name="n",
            slug=f"n-{uuid.uuid4().hex[:8]}",
            host="h",
            port=443,
            status=NodeStatus.ACTIVE,
            max_users=10,
            node_metadata={},
        )
        session.add(node)
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
        return assignment.id, node.id


async def test_refresh_populates_cache(db: Database, cache: RedisCache) -> None:
    await _seed(db)
    providers = build_registry()
    summary = await refresh_summary(db, cache, providers, ttl_seconds=60)
    assert summary["active_users"] == 1
    assert summary["active_nodes"] == 1
    assert summary["active_assignments"] == 1
    cached = await MetricsSummaryCache(cache, providers).read()
    assert cached is not None
    assert cached["active_assignments"] == 1


async def test_scrape_reads_from_cache_no_db(db: Database, cache: RedisCache) -> None:
    await _seed(db)
    providers = build_registry()
    await refresh_summary(db, cache, providers, ttl_seconds=60)
    service = MonitoringService(db.sessionmaker(), providers, cache=cache)
    snapshot = await service.snapshot()
    assert snapshot.get("active_assignments") == 1


async def test_stale_cache_falls_back_to_live(db: Database, cache: RedisCache) -> None:
    await _seed(db)
    providers = build_registry()
    service = MonitoringService(db.sessionmaker(), providers, cache=cache)
    snapshot = await service.snapshot()
    assert snapshot.get("active_users") == 1
    cached = await MetricsSummaryCache(cache, providers).read()
    assert cached is not None


async def test_aggregation_correctness_traffic(db: Database, cache: RedisCache) -> None:
    assignment_id, node_id = await _seed(db)
    async with db.session() as session:
        batch = TrafficBatch(
            node_id=node_id,
            batch_id="b",
            samples=(
                TrafficSample(
                    assignment_id=assignment_id,
                    upload_bytes=300,
                    download_bytes=200,
                    collected_at=datetime(2026, 1, 1, tzinfo=UTC),
                ),
            ),
        )
        await TrafficService(session).ingest(batch)
    providers = build_registry()
    summary = await refresh_summary(db, cache, providers, ttl_seconds=60)
    assert summary["total_traffic_bytes"] == 500
    async with db.session() as session:
        totals = await TrafficRepository(session).totals()
    assert totals.total_bytes == 500


async def test_cache_miss_self_heals(db: Database, cache: RedisCache) -> None:
    await _seed(db)
    providers = build_registry()
    service = MonitoringService(db.sessionmaker(), providers, cache=cache)
    first = await service.snapshot()
    assert first.get("active_users") == 1
    cached = await MetricsSummaryCache(cache, providers).read()
    assert cached is not None
