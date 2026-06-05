from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.client_assignment import ClientAssignment
from app.events.bus import EventBus
from app.events.models import TrafficLimitReached
from app.traffic.collector import TrafficCollector
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
    ) -> None:
        self._session = session
        self._repo = TrafficRepository(session)
        self._events = events
        self._collector = collector or TrafficCollector()

    async def ingest(self, batch: TrafficBatch) -> TrafficIngestResult:
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
        await self._repo.apply_usage_deltas(deltas)
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

    async def totals(self) -> TrafficTotals:
        return await self._repo.totals()

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
        if len(owned) == len(batch.samples):
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
        if self._events is None:
            return
        for assignment_id, delta in deltas.items():
            assignment = owned.get(assignment_id)
            if assignment is None or assignment.traffic_limit_bytes is None:
                continue
            new_total = (assignment.used_bytes or 0) + delta
            if new_total >= assignment.traffic_limit_bytes:
                await self._events.publish(
                    TrafficLimitReached(
                        assignment_id=assignment_id,
                        user_id=assignment.user_id,
                        limit_bytes=assignment.traffic_limit_bytes,
                        used_bytes=new_total,
                    )
                )
