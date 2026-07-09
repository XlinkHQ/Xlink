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
from app.traffic.repository import TrafficRepository
from app.traffic.retention import TrafficRetention
from app.traffic.schemas import TrafficBatch, TrafficSample
from app.traffic.service import TrafficService

# A fixed point well in the past so every ingested sample falls in a CLOSED hour
# bucket relative to "now" — the rollup only compacts closed hours.
BASE = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


async def _seed(app_state: AppState, *, usage_coefficient: float = 1.0) -> dict:
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
        ids["profile_id"] = profile.id
        assignment = ClientAssignment(
            user_id=user.id,
            profile_id=profile.id,
            node_id=node.id,
            provider_kind=ProviderKind.XRAY,
            status=AssignmentStatus.ACTIVE,
        )
        session.add(assignment)
        await session.flush()
        ids["assignment_id"] = assignment.id
    return ids


def _batch(node_id, assignment_id, *, count, start, minutes_step=1, batch_id="b"):
    samples = tuple(
        TrafficSample(
            assignment_id=assignment_id,
            upload_bytes=100,
            download_bytes=200,
            collected_at=start + timedelta(minutes=i * minutes_step),
        )
        for i in range(count)
    )
    return TrafficBatch(node_id=node_id, batch_id=batch_id, samples=samples)


async def _ingest(app_state, batch):
    async with app_state.db.session() as session:
        await TrafficService(session).ingest(batch)


async def test_rollup_populates_hourly(app_state: AppState):
    ids = await _seed(app_state)
    # 5 samples in one hour → one hourly bucket for the assignment.
    await _ingest(app_state, _batch(ids["node_id"], ids["assignment_id"], count=5, start=BASE))
    async with app_state.db.session() as session:
        written = await TrafficService(session).rollup_hourly(now=datetime.now(UTC))
    assert written == 1
    async with app_state.db.session() as session:
        repo = TrafficRepository(session)
        assert await repo.hourly_count() == 1


async def test_rollup_is_idempotent(app_state: AppState):
    ids = await _seed(app_state)
    await _ingest(app_state, _batch(ids["node_id"], ids["assignment_id"], count=4, start=BASE))
    now = datetime.now(UTC)
    async with app_state.db.session() as session:
        await TrafficService(session).rollup_hourly(now=now)
    # Re-run the rollup twice more over the same closed window.
    async with app_state.db.session() as session:
        await TrafficService(session).rollup_hourly(now=now)
    async with app_state.db.session() as session:
        await TrafficService(session).rollup_hourly(now=now)
    async with app_state.db.session() as session:
        repo = TrafficRepository(session)
        # Still exactly one bucket, totals not multiplied.
        assert await repo.hourly_count() == 1
        total = await repo.usage_total_for_profile(ids["profile_id"])
    assert total == 4 * 300  # 4 samples * (100 up + 200 down)


async def test_rollup_matches_raw_totals(app_state: AppState):
    """A usage query must return the SAME total whether served from raw (before
    rollup) or from the rollup (after rollup + raw purge)."""
    ids = await _seed(app_state)
    # Two different hours, several samples each.
    await _ingest(
        app_state,
        _batch(ids["node_id"], ids["assignment_id"], count=6, start=BASE, batch_id="h1"),
    )
    await _ingest(
        app_state,
        _batch(
            ids["node_id"],
            ids["assignment_id"],
            count=6,
            start=BASE + timedelta(hours=2),
            batch_id="h2",
        ),
    )

    # Before rollup: served entirely from raw (watermark NULL → boundary=now).
    async with app_state.db.session() as session:
        raw_total = await TrafficService(session).usage_total_for_profile(ids["profile_id"])
        raw_by_node = await TrafficService(session).usage_by_node()
    expected = 12 * 300
    assert raw_total == expected
    assert raw_by_node[ids["node_id"]] == expected

    # Roll up the closed hours.
    async with app_state.db.session() as session:
        await TrafficService(session).rollup_hourly(now=datetime.now(UTC))

    # After rollup, drop ALL raw rows to prove the read is served from the rollup.
    async with app_state.db.session() as session:
        from sqlalchemy import delete

        from app.traffic.models import TrafficRecord

        await session.execute(delete(TrafficRecord))
        await session.commit()

    async with app_state.db.session() as session:
        rollup_total = await TrafficService(session).usage_total_for_profile(ids["profile_id"])
        rollup_by_node = await TrafficService(session).usage_by_node()
        totals = await TrafficRepository(session).totals()
    assert rollup_total == expected
    assert rollup_by_node[ids["node_id"]] == expected
    assert totals.total_bytes == expected


async def test_rollup_coefficient_weighting(app_state: AppState):
    ids = await _seed(app_state, usage_coefficient=2.0)
    await _ingest(app_state, _batch(ids["node_id"], ids["assignment_id"], count=3, start=BASE))
    async with app_state.db.session() as session:
        await TrafficService(session).rollup_hourly(now=datetime.now(UTC))
    async with app_state.db.session() as session:
        from sqlalchemy import delete

        from app.traffic.models import TrafficRecord

        await session.execute(delete(TrafficRecord))
        await session.commit()
    async with app_state.db.session() as session:
        by_node = await TrafficService(session).usage_by_node()
    # raw stored bytes = 3*300 = 900; weighted by coefficient 2.0 → 1800.
    assert by_node[ids["node_id"]] == 1800


async def test_rollup_excludes_current_hour(app_state: AppState):
    ids = await _seed(app_state)
    now = datetime.now(UTC)
    # A sample in the CURRENT (in-progress) hour must not be rolled up.
    await _ingest(
        app_state,
        _batch(ids["node_id"], ids["assignment_id"], count=1, start=now, batch_id="cur"),
    )
    async with app_state.db.session() as session:
        written = await TrafficService(session).rollup_hourly(now=now)
    assert written == 0
    async with app_state.db.session() as session:
        # But the read still returns it (served from raw, current window).
        total = await TrafficService(session).usage_total_for_profile(ids["profile_id"])
    assert total == 300


async def test_hourly_series_hybrid_raw_and_rollup(app_state: AppState):
    ids = await _seed(app_state)
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    old_hour = now - timedelta(hours=3)
    # One closed-hour sample and one current-hour sample.
    await _ingest(
        app_state,
        _batch(ids["node_id"], ids["assignment_id"], count=2, start=old_hour, batch_id="old"),
    )
    await _ingest(
        app_state,
        _batch(
            ids["node_id"],
            ids["assignment_id"],
            count=1,
            start=now + timedelta(minutes=5),
            batch_id="new",
        ),
    )
    async with app_state.db.session() as session:
        await TrafficService(session).rollup_hourly(now=datetime.now(UTC))
    async with app_state.db.session() as session:
        rows = await TrafficService(session).usage_hourly_for_node(ids["node_id"], hours=24)
    # Both hours present, summing to all three samples, no double counting.
    assert sum(up + dn for _, up, dn in rows) == 3 * 300


async def test_retention_keeps_rollup_drops_raw(app_state: AppState):
    ids = await _seed(app_state)
    now = datetime(2026, 6, 1, tzinfo=UTC)
    old = now - timedelta(days=30)
    await _ingest(
        app_state,
        _batch(ids["node_id"], ids["assignment_id"], count=3, start=old, batch_id="old"),
    )
    # Roll up (relative to now) so the watermark is past the old samples.
    async with app_state.db.session() as session:
        await TrafficService(session).rollup_hourly(now=now)
    # raw_retention=7d drops the 30d-old raw; rollup_retention=90d keeps rollup.
    async with app_state.db.session() as session:
        await TrafficRetention(
            session, retention_days=90, raw_retention_days=7
        ).purge(now=now)
    async with app_state.db.session() as session:
        repo = TrafficRepository(session)
        assert await repo.count() == 0  # raw gone
        assert await repo.hourly_count() == 1  # rollup kept
        total = await repo.usage_total_for_profile(ids["profile_id"])
    assert total == 3 * 300  # analytics still correct from rollup


async def test_retention_never_drops_raw_past_watermark(app_state: AppState):
    """Raw newer than the rollup watermark must survive even if older than the
    raw cutoff, otherwise its usage would be lost (not yet in any rollup)."""
    ids = await _seed(app_state)
    now = datetime(2026, 6, 1, tzinfo=UTC)
    old = now - timedelta(days=30)
    await _ingest(
        app_state,
        _batch(ids["node_id"], ids["assignment_id"], count=2, start=old, batch_id="unrolled"),
    )
    # NO rollup run → watermark is NULL. Retention must not delete raw.
    async with app_state.db.session() as session:
        await TrafficRetention(
            session, retention_days=90, raw_retention_days=7
        ).purge(now=now)
    async with app_state.db.session() as session:
        assert await TrafficRepository(session).count() == 2
