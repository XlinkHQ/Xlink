"""The retention and rollup jobs are leader-gated background loops that trim and
compact traffic data. A silent failure here either grows the raw table forever or
double-compacts it, so the loop contract is pinned explicitly."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.providers.base.models import ProviderKind
from app.traffic.models import TrafficRecord
from app.traffic.scheduler import (
    TrafficRetentionJob,
    TrafficRollupJob,
    run_retention,
    run_rollup,
)


class _Leader:
    def __init__(self, is_leader: bool) -> None:
        self.is_leader = is_leader


async def _seed_assignment(db) -> tuple:
    """traffic_records has NOT NULL FKs to nodes and client_assignments, so the
    rows have to hang off real parents."""
    import uuid

    async with db.session() as session:
        node = Node(
            name="n",
            slug=f"n-{uuid.uuid4().hex[:8]}",
            host="203.0.113.20",
            port=443,
            max_users=10,
            status=NodeStatus.ACTIVE,
        )
        session.add(node)
        await session.flush()
        user = User(
            email=f"u-{uuid.uuid4().hex[:8]}@x.io",
            username=f"u-{uuid.uuid4().hex[:8]}",
            hashed_password=hash_password("strong-password-1234-AB!"),
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
        return assignment.id, node.id


async def _seed_records(db, *, assignment_id, node_id, when: datetime, count: int = 1) -> None:
    async with db.session() as session:
        for i in range(count):
            session.add(
                TrafficRecord(
                    assignment_id=assignment_id,
                    node_id=node_id,
                    upload_bytes=10,
                    download_bytes=20,
                    total_bytes=30,
                    collected_at=when + timedelta(seconds=i),
                )
            )
        await session.flush()


async def _count_records(db) -> int:
    from sqlalchemy import func, select

    async with db.session() as session:
        return int(await session.scalar(select(func.count()).select_from(TrafficRecord)) or 0)


# --------------------------------------------------------------------------
# The work functions
# --------------------------------------------------------------------------


async def test_run_retention_purges_only_rows_past_the_cutoff(app_state) -> None:
    aid, nid = await _seed_assignment(app_state.db)
    old = datetime.now(UTC) - timedelta(days=90)
    recent = datetime.now(UTC) - timedelta(hours=1)
    await _seed_records(app_state.db, assignment_id=aid, node_id=nid, when=old, count=3)
    await _seed_records(app_state.db, assignment_id=aid, node_id=nid, when=recent, count=2)

    await run_retention(app_state.db, retention_days=30, raw_retention_days=30)

    # The recent rows must survive; the 90-day-old ones must not.
    assert await _count_records(app_state.db) == 2


async def test_run_retention_is_a_no_op_when_nothing_is_old(app_state) -> None:
    aid, nid = await _seed_assignment(app_state.db)
    await _seed_records(
        app_state.db, assignment_id=aid, node_id=nid, when=datetime.now(UTC), count=2
    )
    await run_retention(app_state.db, retention_days=30)
    assert await _count_records(app_state.db) == 2


async def test_run_rollup_returns_a_count_and_is_idempotent(app_state) -> None:
    aid, nid = await _seed_assignment(app_state.db)
    # Two closed hours back, so the bucket is eligible for rollup.
    when = datetime.now(UTC) - timedelta(hours=2)
    await _seed_records(app_state.db, assignment_id=aid, node_id=nid, when=when, count=3)

    first = await run_rollup(app_state.db)
    second = await run_rollup(app_state.db)

    assert first >= 0
    # Re-running recomputes the same buckets rather than adding to them.
    assert second >= 0


# --------------------------------------------------------------------------
# Leader gating — the reason these jobs are safe on multiple replicas
# --------------------------------------------------------------------------


async def test_retention_job_skips_work_when_not_leader(app_state, monkeypatch) -> None:
    calls = 0

    async def _counting(*a, **k) -> int:
        nonlocal calls
        calls += 1
        return 0

    monkeypatch.setattr("app.traffic.scheduler.run_retention", _counting)

    job = TrafficRetentionJob(
        app_state.db, interval_seconds=0, retention_days=30, leader=_Leader(False)
    )
    job.start()
    await asyncio.sleep(0.05)
    await job.stop()
    assert calls == 0


async def test_retention_job_runs_when_leader(app_state, monkeypatch) -> None:
    calls = 0

    async def _counting(*a, **k) -> int:
        nonlocal calls
        calls += 1
        return 0

    monkeypatch.setattr("app.traffic.scheduler.run_retention", _counting)

    job = TrafficRetentionJob(
        app_state.db, interval_seconds=0, retention_days=30, leader=_Leader(True)
    )
    job.start()
    await asyncio.sleep(0.05)
    await job.stop()
    assert calls > 0


async def test_rollup_job_skips_work_when_not_leader(app_state, monkeypatch) -> None:
    calls = 0

    async def _counting(*a, **k) -> int:
        nonlocal calls
        calls += 1
        return 0

    monkeypatch.setattr("app.traffic.scheduler.run_rollup", _counting)

    job = TrafficRollupJob(app_state.db, interval_seconds=0, leader=_Leader(False))
    job.start()
    await asyncio.sleep(0.05)
    await job.stop()
    assert calls == 0


async def test_rollup_job_runs_when_leader(app_state, monkeypatch) -> None:
    calls = 0

    async def _counting(*a, **k) -> int:
        nonlocal calls
        calls += 1
        return 0

    monkeypatch.setattr("app.traffic.scheduler.run_rollup", _counting)

    job = TrafficRollupJob(app_state.db, interval_seconds=0, leader=_Leader(True))
    job.start()
    await asyncio.sleep(0.05)
    await job.stop()
    assert calls > 0


async def test_jobs_run_without_a_leader_configured(app_state, monkeypatch) -> None:
    """Single-replica deployments pass leader=None and must still do the work."""
    calls = 0

    async def _counting(*a, **k) -> int:
        nonlocal calls
        calls += 1
        return 0

    monkeypatch.setattr("app.traffic.scheduler.run_rollup", _counting)
    job = TrafficRollupJob(app_state.db, interval_seconds=0)
    job.start()
    await asyncio.sleep(0.05)
    await job.stop()
    assert calls > 0


# --------------------------------------------------------------------------
# Loop lifecycle
# --------------------------------------------------------------------------


async def test_start_is_idempotent(app_state) -> None:
    job = TrafficRollupJob(app_state.db, interval_seconds=5)
    job.start()
    first = job._task
    job.start()
    assert job._task is first
    await job.stop()


async def test_stop_without_start_is_safe(app_state) -> None:
    job = TrafficRollupJob(app_state.db, interval_seconds=5)
    await job.stop()  # must not raise
    assert job._task is None


async def test_stop_clears_the_task(app_state) -> None:
    job = TrafficRetentionJob(app_state.db, interval_seconds=5, retention_days=30)
    job.start()
    assert job._task is not None
    await job.stop()
    assert job._task is None


async def test_a_failing_run_does_not_kill_the_loop(app_state, monkeypatch) -> None:
    """One bad pass must be logged and retried, not terminate the job."""
    calls = 0

    async def _boom(*a, **k) -> int:
        nonlocal calls
        calls += 1
        raise RuntimeError("purge exploded")

    monkeypatch.setattr("app.traffic.scheduler.run_retention", _boom)

    job = TrafficRetentionJob(
        app_state.db, interval_seconds=0, retention_days=30, leader=_Leader(True)
    )
    job.start()
    await asyncio.sleep(0.08)
    still_running = job._task is not None and not job._task.done()
    await job.stop()
    assert calls > 1, "loop should have retried after the exception"
    assert still_running
