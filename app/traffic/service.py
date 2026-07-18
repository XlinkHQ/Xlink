from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import CacheProtocol
from app.core.logging import get_logger
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node
from app.domain.user import User
from app.events.bus import EventBus
from app.events.models import TrafficLimitReached
from app.traffic.collector import TrafficCollector
from app.traffic.models import TrafficRecord
from app.traffic.repository import TrafficRepository
from app.traffic.schemas import TrafficBatch, TrafficIngestResult, TrafficTotals, TrafficUsage

logger = get_logger("xlink.traffic")


class TrafficService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        events: EventBus | None = None,
        collector: TrafficCollector | None = None,
        cache: CacheProtocol | None = None,
        reader_session: AsyncSession | None = None,
    ) -> None:
        self._session = session
        # reader_session (when a replica is configured) carries only the pure
        # analytics reads; None → the repo uses the primary session for them,
        # identical to before. Writes/ingest/rollup always use `session`.
        self._repo = TrafficRepository(session, reader_session=reader_session)
        self._events = events
        self._collector = collector or TrafficCollector()
        self._cache = cache

    async def ingest(self, batch: TrafficBatch) -> TrafficIngestResult:
        attempts = 3
        for attempt in range(attempts):
            try:
                return await self._ingest_once(batch)
            except DBAPIError as exc:
                if not getattr(exc.orig, "sqlstate", None) == "40P01" and "deadlock" not in str(
                    exc
                ).lower():
                    raise
                await self._session.rollback()
                if attempt == attempts - 1:
                    logger.warning("traffic_ingest_deadlock_giveup", batch_id=batch.batch_id)
                    raise
                await asyncio.sleep(0.05 * (attempt + 1))
        raise RuntimeError("unreachable")

    async def _ingest_once(self, batch: TrafficBatch) -> TrafficIngestResult:
        # Idempotency gate: a resent or concurrently-duplicated batch (same
        # deterministic batch_id) is claimed once; a repeat is a no-op so usage
        # deltas are never double-applied.
        if batch.batch_id and not await self._repo.claim_batch(batch.node_id, batch.batch_id):
            logger.info(
                "traffic_batch_duplicate", node_id=str(batch.node_id), batch_id=batch.batch_id
            )
            return TrafficIngestResult(
                node_id=batch.node_id,
                batch_id=batch.batch_id,
                received=len(batch.samples),
                inserted=0,
                duplicates=len(batch.samples),
                skipped=0,
            )
        owned = await self._owned_assignment_ids(batch)
        filtered = self._filter_to_owned(batch, owned)
        prepared = self._collector.prepare(filtered)
        # bulk_insert applies ON CONFLICT DO NOTHING and returns the per-assignment
        # sum of bytes for the rows it ACTUALLY inserted (RETURNING). Usage deltas
        # come from that, not a pre-insert existing-keys snapshot: a snapshot
        # races two concurrent batches that carry the same sample under different
        # batch_ids (both see it absent → both count it, but only one row
        # survives → double-count). RETURNING attributes each row's bytes to the
        # one transaction that inserted it.
        deltas, inserted = await self._repo.bulk_insert(prepared.rows)
        duplicates = len(prepared.rows) - inserted + prepared.deduped
        skipped = prepared.skipped + (len(batch.samples) - len(filtered.samples))

        node = await self._session.get(Node, batch.node_id)
        coeff = node.usage_coefficient if node is not None else 1.0
        if coeff != 1.0:
            deltas = {aid: round(d * coeff) for aid, d in deltas.items()}
        await self._repo.apply_usage_deltas(deltas)
        # Refresh the just-updated columns in ONE query instead of a per-assignment
        # session.refresh() (which issued one SELECT each on this hot path). The
        # UPDATE ran with synchronize_session=False, so the ORM copies are stale;
        # pull fresh values with a single IN and write them back in-memory.
        owned_ids = [aid for aid in deltas if aid in owned]
        if owned_ids:
            fresh = (
                await self._session.execute(
                    select(
                        ClientAssignment.id,
                        ClientAssignment.used_bytes,
                        ClientAssignment.traffic_limit_bytes,
                    ).where(ClientAssignment.id.in_(owned_ids))
                )
            ).all()
            for aid, used, limit in fresh:
                obj = owned[aid]
                obj.used_bytes = used
                obj.traffic_limit_bytes = limit
        await self._check_limits(owned, deltas)
        logger.info(
            "traffic_ingested",
            node_id=str(batch.node_id),
            batch_id=batch.batch_id,
            received=prepared.received,
            inserted=inserted,
            duplicates=duplicates,
            skipped=skipped,
        )
        return TrafficIngestResult(
            node_id=batch.node_id,
            batch_id=batch.batch_id,
            received=len(batch.samples),
            inserted=inserted,
            duplicates=duplicates,
            skipped=skipped,
        )

    async def rollup_hourly(self, *, now: datetime | None = None) -> int:
        """Aggregate raw traffic_records into the hourly rollup for all CLOSED
        hour buckets since the last watermark, then advance the watermark to the
        current hour. Idempotent: buckets are upserted with the recomputed SUM,
        so a re-run (or overlapping run) recomputes the same totals rather than
        adding to them. Returns the number of (assignment, bucket) rows written.

        The current (in-progress) hour is intentionally NOT rolled up — it is
        still receiving samples and analytics reads serve it from raw. The
        watermark it advances to is the raw/rollup read boundary."""
        reference = now or datetime.now(UTC)
        floor_hour = reference.replace(minute=0, second=0, microsecond=0)
        watermark = await self._repo.get_rollup_watermark()
        # Re-aggregate from one hour before the watermark to absorb any raw rows
        # that landed late for the boundary hour; ON CONFLICT recompute makes the
        # overlap safe (no double-count). On first run (no watermark) aggregate
        # everything closed.
        since = (watermark - timedelta(hours=1)) if watermark is not None else None
        # A node re-delivering hours/days-old WAL lands raw rows in buckets BELOW
        # that window. Because the rollup upsert RECOMPUTES each bucket's SUM
        # (idempotent), it is safe to lower `since` to the oldest such late row so
        # its usage is folded into traffic_hourly before the raw rows are purged —
        # otherwise it is lost from the rollup permanently. Bounded by raw
        # retention: no raw exists older than the purge cutoff, so the widened
        # window can never scan unbounded history.
        if since is not None:
            oldest_late = await self._repo.min_raw_collected_at_before(since)
            if oldest_late is not None:
                since = oldest_late.replace(minute=0, second=0, microsecond=0)
        written = await self._repo.rollup_hourly(floor_hour=floor_hour, since=since)
        await self._repo.set_rollup_watermark(floor_hour)
        await self._session.commit()
        return written

    async def usage_for_assignment(self, assignment_id: uuid.UUID) -> TrafficUsage:
        return await self._repo.usage_for_assignment(assignment_id)

    async def reset_user(self, user_id: uuid.UUID) -> int:
        count = await self._repo.reset_for_user(user_id)
        user = await self._session.get(User, user_id)
        if user is None:
            return count
        await self._session.execute(
            update(User)
            .where(User.id == user_id)
            .values(users_data_usage=0)
            .execution_options(synchronize_session=False)
        )
        node_ids: list[uuid.UUID] = []
        if user.is_active and not user.removed:
            node_ids = await self._repo.reactivate_disabled_assignments(user_id)
            # LIMITED→ACTIVE brought slots back; recompute so current_users is right.
            await self._resync_node_counts(node_ids)
        await self._session.flush()
        await self._wake_nodes(node_ids, user_ids=[user_id])
        return count

    async def usage_for_users(
        self, user_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[int, int, bool]]:
        return await self._repo.usage_for_users(user_ids)

    async def totals(self) -> TrafficTotals:
        return await self._repo.totals()

    async def usage_by_node(self) -> dict[uuid.UUID, int]:
        return await self._repo.usage_by_node()

    async def usage_by_node_user(self, node_id: uuid.UUID) -> list[tuple[uuid.UUID, int]]:
        return await self._repo.usage_by_node_user(node_id)

    async def usage_by_user_node(self, user_id: uuid.UUID) -> list[tuple[uuid.UUID, str, int]]:
        return await self._repo.usage_by_user_node(user_id)

    async def usage_series_for_user(
        self, user_id: uuid.UUID, days: int = 14
    ) -> list[tuple[str, int, int]]:
        since = datetime.now(UTC) - timedelta(days=max(1, days))
        return await self._repo.usage_series_for_user(user_id, since)

    async def usage_hourly_for_node(
        self, node_id: uuid.UUID, hours: int = 24
    ) -> list[tuple[str, int, int]]:
        since = datetime.now(UTC) - timedelta(hours=max(1, hours))
        return await self._repo.usage_hourly_for_node(node_id, since)

    async def usage_hourly_for_profile(
        self, profile_id: uuid.UUID, hours: int = 24
    ) -> list[tuple[str, int, int]]:
        since = datetime.now(UTC) - timedelta(hours=max(1, hours))
        return await self._repo.usage_hourly_for_profile(profile_id, since)

    async def usage_total_for_profile(self, profile_id: uuid.UUID) -> int:
        return await self._repo.usage_total_for_profile(profile_id)

    async def online_user_ids(self, window_seconds: int = 45) -> set[uuid.UUID]:
        cutoff = datetime.now(UTC) - timedelta(seconds=max(1, window_seconds))
        stmt = (
            select(ClientAssignment.user_id)
            .join(TrafficRecord, TrafficRecord.assignment_id == ClientAssignment.id)
            .where(
                TrafficRecord.collected_at >= cutoff,
                ClientAssignment.status == AssignmentStatus.ACTIVE,
            )
            .distinct()
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return set(rows)

    async def last_seen_for_users(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, datetime]:
        if not user_ids:
            return {}
        stmt = (
            select(ClientAssignment.user_id, func.max(TrafficRecord.collected_at))
            .join(TrafficRecord, TrafficRecord.assignment_id == ClientAssignment.id)
            .where(ClientAssignment.user_id.in_(user_ids))
            .group_by(ClientAssignment.user_id)
        )
        rows = (await self._session.execute(stmt)).all()
        return {uid: ts for uid, ts in rows if ts is not None}

    async def _owned_assignment_ids(self, batch: TrafficBatch) -> dict[uuid.UUID, ClientAssignment]:
        ids = {sample.assignment_id for sample in batch.samples}
        if not ids:
            return {}
        stmt = select(ClientAssignment).where(
            ClientAssignment.id.in_(ids),
            ClientAssignment.node_id == batch.node_id,
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return {row.id: row for row in rows}

    def _filter_to_owned(
        self, batch: TrafficBatch, owned: dict[uuid.UUID, ClientAssignment]
    ) -> TrafficBatch:
        if all(s.assignment_id in owned for s in batch.samples):
            return batch
        kept = tuple(s for s in batch.samples if s.assignment_id in owned)
        return TrafficBatch(node_id=batch.node_id, batch_id=batch.batch_id, samples=kept)

    async def _check_limits(
        self,
        owned: dict[uuid.UUID, ClientAssignment],
        deltas: dict[uuid.UUID, int],
    ) -> None:
        # Persist user usage to the DB first so both the per-assignment and the
        # per-user limit checks below decide from the same, freshly-written view.
        await self._bump_user_usage(owned, deltas)
        for assignment_id in deltas:
            assignment = owned.get(assignment_id)
            if assignment is None or assignment.traffic_limit_bytes is None:
                continue
            new_total = assignment.used_bytes or 0
            if new_total >= assignment.traffic_limit_bytes:
                transitioned = await self._enforce_limit(assignment)
                if transitioned and self._events is not None:
                    await self._events.publish(
                        TrafficLimitReached(
                            assignment_id=assignment_id,
                            user_id=assignment.user_id,
                            limit_bytes=assignment.traffic_limit_bytes,
                            used_bytes=new_total,
                        )
                    )
        await self._enforce_user_limits(self._delta_user_ids(owned, deltas))

    @staticmethod
    def _delta_user_ids(
        owned: dict[uuid.UUID, ClientAssignment],
        deltas: dict[uuid.UUID, int],
    ) -> list[uuid.UUID]:
        return sorted(
            {owned[aid].user_id for aid in deltas if aid in owned and deltas[aid] > 0}
        )

    async def _bump_user_usage(
        self,
        owned: dict[uuid.UUID, ClientAssignment],
        deltas: dict[uuid.UUID, int],
    ) -> None:
        user_ids = self._delta_user_ids(owned, deltas)
        if not user_ids:
            return
        totals = await self._repo.usage_sum_by_user(user_ids)
        # One UPDATE with a per-user CASE instead of a UPDATE per user on the
        # ingest hot path.
        ids = list(user_ids)
        await self._session.execute(
            update(User)
            .where(User.id.in_(ids))
            .values(
                users_data_usage=case(
                    {uid: totals.get(uid, 0) for uid in ids},
                    value=User.id,
                    else_=0,
                )
            )
            .execution_options(synchronize_session=False)
        )
        await self._session.flush()

    async def _enforce_user_limits(self, user_ids: Sequence[uuid.UUID]) -> None:
        rows = (
            await self._session.execute(
                select(User).where(
                    User.id.in_(user_ids),
                    User.data_limit_bytes.isnot(None),
                    User.users_data_usage >= User.data_limit_bytes,
                )
            )
        ).scalars().all()
        if not rows:
            return
        over = [u.id for u in rows]
        node_rows = await self._session.execute(
            select(ClientAssignment.node_id)
            .where(
                ClientAssignment.user_id.in_(over),
                ClientAssignment.status == AssignmentStatus.ACTIVE,
            )
            .distinct()
        )
        node_ids = [nid for (nid,) in node_rows.all() if nid is not None]
        await self._session.execute(
            update(ClientAssignment)
            .where(
                ClientAssignment.user_id.in_(over),
                ClientAssignment.status == AssignmentStatus.ACTIVE,
            )
            .values(status=AssignmentStatus.LIMITED)
            .execution_options(synchronize_session=False)
        )
        await self._resync_node_counts(node_ids)
        await self._session.flush()
        await self._wake_nodes(node_ids, user_ids=over)

    async def _enforce_limit(self, assignment: ClientAssignment) -> bool:
        if assignment.status is not AssignmentStatus.ACTIVE:
            return False
        assignment.status = AssignmentStatus.LIMITED
        await self._session.flush()
        if assignment.node_id is not None:
            await self._resync_node_counts([assignment.node_id])
            await self._wake_nodes([assignment.node_id], user_ids=[assignment.user_id])
        return True

    async def _resync_node_counts(self, node_ids: Sequence[uuid.UUID]) -> None:
        # Recompute current_users from a COUNT of ACTIVE assignments rather than
        # maintaining fragile ±1 deltas that drift when transitions are missed
        # (e.g. LIMITED→ACTIVE on reset never re-incremented).
        ids = [nid for nid in node_ids if nid is not None]
        if not ids:
            return
        active_count = (
            select(func.count())
            .select_from(ClientAssignment)
            .where(
                ClientAssignment.node_id == Node.id,
                ClientAssignment.status == AssignmentStatus.ACTIVE,
            )
            .scalar_subquery()
        )
        await self._session.execute(
            update(Node)
            .where(Node.id.in_(ids))
            .values(current_users=active_count)
            .execution_options(synchronize_session=False)
        )
        await self._session.flush()

    async def _wake_nodes(
        self, node_ids: Sequence[uuid.UUID], user_ids: Sequence[uuid.UUID] = ()
    ) -> None:
        if self._cache is None:
            return
        # Invalidate only the affected users' cached feeds (subscription:{uid}:*)
        # instead of scanning/wiping the entire keyspace on the traffic hot path.
        for uid in set(user_ids):
            keys = [
                key async for key in self._cache.client.scan_iter(match=f"subscription:{uid}:*")
            ]
            if keys:
                await self._cache.client.delete(*keys)
        for nid in node_ids:
            await self._cache.publish_node_event(nid, "config_changed")
