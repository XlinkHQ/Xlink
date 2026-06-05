from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.traffic.models import TrafficRecord
from app.traffic.schemas import TrafficTotals, TrafficUsage


class TrafficRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def apply_usage_deltas(self, deltas: dict[uuid.UUID, int]) -> None:
        if not deltas:
            return
        from app.domain.client_assignment import ClientAssignment

        whens = {aid: ClientAssignment.used_bytes + delta for aid, delta in deltas.items()}
        stmt = (
            update(ClientAssignment)
            .where(ClientAssignment.id.in_(list(deltas)))
            .values(used_bytes=case(whens, value=ClientAssignment.id))
            .execution_options(synchronize_session=False)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def bulk_insert(self, rows: Sequence[dict]) -> int:
        if not rows:
            return 0
        dialect = self.session.bind.dialect.name if self.session.bind else "postgresql"
        if dialect == "sqlite":
            stmt = sqlite_insert(TrafficRecord).values(list(rows))
            stmt = stmt.on_conflict_do_nothing(index_elements=["assignment_id", "collected_at"])
        else:
            stmt = pg_insert(TrafficRecord).values(list(rows))
            stmt = stmt.on_conflict_do_nothing(constraint="uq_traffic_records_assignment_collected")
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount if result.rowcount is not None and result.rowcount >= 0 else 0

    async def usage_for_assignment(self, assignment_id: uuid.UUID) -> TrafficUsage:
        stmt = select(
            func.coalesce(func.sum(TrafficRecord.upload_bytes), 0),
            func.coalesce(func.sum(TrafficRecord.download_bytes), 0),
            func.coalesce(func.sum(TrafficRecord.total_bytes), 0),
            func.count(),
        ).where(TrafficRecord.assignment_id == assignment_id)
        up, down, total, count = (await self.session.execute(stmt)).one()
        return TrafficUsage(
            assignment_id=assignment_id,
            upload_bytes=int(up),
            download_bytes=int(down),
            total_bytes=int(total),
            sample_count=int(count),
        )

    async def totals(self) -> TrafficTotals:
        stmt = select(
            func.coalesce(func.sum(TrafficRecord.total_bytes), 0),
            func.coalesce(func.sum(TrafficRecord.upload_bytes), 0),
            func.coalesce(func.sum(TrafficRecord.download_bytes), 0),
            func.count(),
        )
        total, up, down, count = (await self.session.execute(stmt)).one()
        return TrafficTotals(
            total_bytes=int(total),
            upload_bytes=int(up),
            download_bytes=int(down),
            record_count=int(count),
        )

    async def totals_since(self, since: datetime) -> TrafficTotals:
        stmt = select(
            func.coalesce(func.sum(TrafficRecord.total_bytes), 0),
            func.coalesce(func.sum(TrafficRecord.upload_bytes), 0),
            func.coalesce(func.sum(TrafficRecord.download_bytes), 0),
            func.count(),
        ).where(TrafficRecord.collected_at >= since)
        total, up, down, count = (await self.session.execute(stmt)).one()
        return TrafficTotals(
            total_bytes=int(total),
            upload_bytes=int(up),
            download_bytes=int(down),
            record_count=int(count),
        )

    async def list_for_assignment(
        self,
        assignment_id: uuid.UUID,
        *,
        limit: int = 100,
        before: datetime | None = None,
    ) -> Sequence[TrafficRecord]:
        stmt = select(TrafficRecord).where(TrafficRecord.assignment_id == assignment_id)
        if before is not None:
            stmt = stmt.where(TrafficRecord.collected_at < before)
        stmt = stmt.order_by(TrafficRecord.collected_at.desc(), TrafficRecord.id.desc()).limit(
            max(1, limit)
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def existing_keys(
        self, assignment_ids: Sequence[uuid.UUID], collected_ats: Sequence[datetime]
    ) -> set[tuple[uuid.UUID, datetime]]:
        if not assignment_ids:
            return set()
        stmt = select(TrafficRecord.assignment_id, TrafficRecord.collected_at).where(
            TrafficRecord.assignment_id.in_(set(assignment_ids)),
            TrafficRecord.collected_at.in_(set(collected_ats)),
        )
        rows = (await self.session.execute(stmt)).all()
        return {(aid, ts) for aid, ts in rows}

    async def delete_before(self, cutoff: datetime) -> int:
        result = await self.session.execute(
            delete(TrafficRecord).where(TrafficRecord.collected_at < cutoff)
        )
        return result.rowcount or 0

    async def count(self) -> int:
        return int(await self.session.scalar(select(func.count()).select_from(TrafficRecord)) or 0)
