from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.redis import RedisCache
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
        cache: RedisCache | None = None,
    ) -> None:
        self._session = session
        self._repo = TrafficRepository(session)
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
        owned = await self._owned_assignment_ids(batch)
        filtered = self._filter_to_owned(batch, owned)
        prepared = self._collector.prepare(filtered)
        before = await self._repo.existing_keys(
            [row["assignment_id"] for row in prepared.rows],
            [row["collected_at"] for row in prepared.rows],
        )
        inserted = await self._repo.bulk_insert(prepared.rows)
        duplicates = len(prepared.rows) - inserted + prepared.deduped
        skipped = prepared.skipped + (len(batch.samples) - len(filtered.samples))
        deltas = self._inserted_deltas(prepared, before)

        node = await self._session.get(Node, batch.node_id)
        coeff = node.usage_coefficient if node is not None else 1.0
        if coeff != 1.0:
            deltas = {aid: round(d * coeff) for aid, d in deltas.items()}
        await self._repo.apply_usage_deltas(deltas)
        for assignment_id in deltas:
            if assignment_id in owned:
                await self._session.refresh(owned[assignment_id], ["used_bytes"])
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

    async def usage_for_assignment(self, assignment_id: uuid.UUID) -> TrafficUsage:
        return await self._repo.usage_for_assignment(assignment_id)

    async def reset_user(self, user_id: uuid.UUID) -> int:
        count = await self._repo.reset_for_user(user_id)
        user = await self._session.get(User, user_id)
        if user is None:
            return count
        user.users_data_usage = 0
        node_ids: list[uuid.UUID] = []
        if user.is_active and not user.removed:
            node_ids = await self._repo.reactivate_disabled_assignments(user_id)
        await self._session.flush()
        await self._wake_nodes(node_ids)
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

    async def online_user_ids(self, window_seconds: int = 90) -> set[uuid.UUID]:
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

    def _inserted_deltas(self, prepared, before: set) -> dict[uuid.UUID, int]:
        deltas: dict[uuid.UUID, int] = {}
        for row in prepared.rows:
            key = (row["assignment_id"], row["collected_at"])
            if key in before:
                continue
            deltas[row["assignment_id"]] = deltas.get(row["assignment_id"], 0) + row["total_bytes"]
        return deltas

    async def _check_limits(
        self,
        owned: dict[uuid.UUID, ClientAssignment],
        deltas: dict[uuid.UUID, int],
    ) -> None:
        for assignment_id, _delta in deltas.items():
            assignment = owned.get(assignment_id)
            if assignment is None or assignment.traffic_limit_bytes is None:
                continue
            new_total = assignment.used_bytes or 0
            if new_total >= assignment.traffic_limit_bytes:
                await self._enforce_limit(assignment)
                if self._events is not None:
                    await self._events.publish(
                        TrafficLimitReached(
                            assignment_id=assignment_id,
                            user_id=assignment.user_id,
                            limit_bytes=assignment.traffic_limit_bytes,
                            used_bytes=new_total,
                        )
                    )
        await self._bump_user_usage(owned, deltas)

    async def _bump_user_usage(
        self,
        owned: dict[uuid.UUID, ClientAssignment],
        deltas: dict[uuid.UUID, int],
    ) -> None:
        user_ids = {
            owned[aid].user_id for aid in deltas if aid in owned and deltas[aid] > 0
        }
        if not user_ids:
            return
        totals = await self._repo.usage_sum_by_user(sorted(user_ids))
        for user_id in sorted(user_ids):
            await self._session.execute(
                update(User)
                .where(User.id == user_id)
                .values(users_data_usage=totals.get(user_id, 0))
                .execution_options(synchronize_session=False)
            )
        await self._session.flush()
        await self._enforce_user_limits(list(user_ids))

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
            .values(status=AssignmentStatus.DISABLED)
            .execution_options(synchronize_session=False)
        )
        await self._session.flush()
        await self._wake_nodes(node_ids)

    async def _enforce_limit(self, assignment: ClientAssignment) -> None:
        if assignment.status is not AssignmentStatus.ACTIVE:
            return
        assignment.status = AssignmentStatus.DISABLED
        await self._session.execute(
            update(Node)
            .where(Node.id == assignment.node_id, Node.current_users > 0)
            .values(current_users=Node.current_users - 1)
            .execution_options(synchronize_session=False)
        )
        await self._session.flush()
        if assignment.node_id is not None:
            await self._wake_nodes([assignment.node_id])

    async def _wake_nodes(self, node_ids: Sequence[uuid.UUID]) -> None:
        if self._cache is None or not node_ids:
            return
        keys = [key async for key in self._cache.client.scan_iter(match="subscription:*")]
        if keys:
            await self._cache.client.delete(*keys)
        for nid in node_ids:
            await self._cache.publish_node_event(nid, "config_changed")
