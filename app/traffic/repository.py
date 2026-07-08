from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import case, delete, func, select, tuple_, update
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

        ordered = sorted(deltas)
        # Single UPDATE with a per-id CASE delta instead of one round-trip per
        # assignment: this is the traffic-ingest hot path (runs on every agent
        # report), so N sequential UPDATEs held the connection and scaled badly
        # with assignments-per-node. One statement, one round-trip.
        delta_case = case(
            {aid: deltas[aid] for aid in ordered},
            value=ClientAssignment.id,
            else_=0,
        )
        updated = ClientAssignment.used_bytes + delta_case
        await self.session.execute(
            update(ClientAssignment)
            .where(ClientAssignment.id.in_(ordered))
            .values(used_bytes=case((updated < 0, 0), else_=updated))
            .execution_options(synchronize_session=False)
        )
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

    async def claim_batch(self, node_id: uuid.UUID, batch_id: str) -> bool:
        """Record (node_id, batch_id) idempotently. Returns True if this call
        claimed it (first time), False if it was already processed — the caller
        should then skip re-applying deltas to avoid double-counting."""
        from app.traffic.models import ProcessedBatch

        dialect = self.session.bind.dialect.name if self.session.bind else "postgresql"
        values = {"node_id": node_id, "batch_id": batch_id}
        if dialect == "sqlite":
            stmt = sqlite_insert(ProcessedBatch).values(values).on_conflict_do_nothing(
                index_elements=["node_id", "batch_id"]
            )
        else:
            stmt = pg_insert(ProcessedBatch).values(values).on_conflict_do_nothing(
                constraint="uq_processed_batches_node_batch"
            )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return bool(result.rowcount)

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

    def _weighted_totals_stmt(self):
        from app.domain.client_assignment import ClientAssignment
        from app.domain.node import Node

        coeff = func.coalesce(Node.usage_coefficient, 1.0)
        return (
            select(
                func.coalesce(func.sum(TrafficRecord.total_bytes * coeff), 0),
                func.coalesce(func.sum(TrafficRecord.upload_bytes * coeff), 0),
                func.coalesce(func.sum(TrafficRecord.download_bytes * coeff), 0),
                func.count(),
            )
            .join(ClientAssignment, ClientAssignment.id == TrafficRecord.assignment_id)
            .join(Node, Node.id == ClientAssignment.node_id)
        )

    async def totals(self) -> TrafficTotals:
        total, up, down, count = (await self.session.execute(self._weighted_totals_stmt())).one()
        return TrafficTotals(
            total_bytes=int(total),
            upload_bytes=int(up),
            download_bytes=int(down),
            record_count=int(count),
        )

    async def totals_since(self, since: datetime) -> TrafficTotals:
        stmt = self._weighted_totals_stmt().where(TrafficRecord.collected_at >= since)
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
        pairs = list(set(zip(assignment_ids, collected_ats, strict=True)))
        stmt = select(TrafficRecord.assignment_id, TrafficRecord.collected_at).where(
            tuple_(TrafficRecord.assignment_id, TrafficRecord.collected_at).in_(pairs),
        )
        rows = (await self.session.execute(stmt)).all()
        return {(aid, ts) for aid, ts in rows}

    async def sum_bytes_before(self, cutoff: datetime) -> dict[uuid.UUID, int]:
        from app.domain.node import Node

        stmt = (
            select(
                TrafficRecord.assignment_id,
                func.coalesce(Node.usage_coefficient, 1.0),
                func.coalesce(func.sum(TrafficRecord.total_bytes), 0),
            )
            .outerjoin(Node, Node.id == TrafficRecord.node_id)
            .where(TrafficRecord.collected_at < cutoff)
            .group_by(TrafficRecord.assignment_id, Node.usage_coefficient)
        )
        rows = (await self.session.execute(stmt)).all()
        totals: dict[uuid.UUID, int] = {}
        for aid, coeff, total in rows:
            adjusted = int(total) if coeff == 1.0 else round(int(total) * float(coeff))
            totals[aid] = totals.get(aid, 0) + adjusted
        return totals

    async def delete_before(self, cutoff: datetime, *, batch: int = 10000) -> int:
        from app.traffic.models import ProcessedBatch

        # Delete in bounded chunks rather than one unbounded DELETE: a full-table
        # purge otherwise takes a long transaction + wide lock on traffic_records,
        # which is also the ingest hot-path table. Each chunk is a small statement;
        # committing per chunk keeps locks short and WAL bounded.
        deleted = 0
        while True:
            sub = (
                select(TrafficRecord.id)
                .where(TrafficRecord.collected_at < cutoff)
                .limit(batch)
            )
            stmt = delete(TrafficRecord).where(
                TrafficRecord.id.in_(sub.scalar_subquery())
            )
            result = await self.session.execute(stmt)
            n = result.rowcount or 0
            deleted += n
            await self.session.commit()
            if n < batch:
                break
            # Yield between chunks so a large backlog purge doesn't monopolize the
            # event loop / a DB connection back-to-back.
            await asyncio.sleep(0)
        # Keep the idempotency ledger LONGER than the records it guards. If a node
        # is offline past the record-retention window and still holds buffered WAL,
        # purging both the records AND its batch_ids at the same cutoff lets the
        # re-delivered batch look brand-new → double-count. Retain ledger 2× longer.
        ledger_cutoff = cutoff - (datetime.now(UTC) - cutoff)
        await self.session.execute(
            delete(ProcessedBatch).where(ProcessedBatch.created_at < ledger_cutoff)
        )
        await self.session.commit()
        return deleted

    async def count(self) -> int:
        return int(await self.session.scalar(select(func.count()).select_from(TrafficRecord)) or 0)

    async def usage_sum_by_user(
        self, user_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        from app.domain.client_assignment import ClientAssignment

        if not user_ids:
            return {}
        rows = (
            await self.session.execute(
                select(
                    ClientAssignment.user_id,
                    func.coalesce(func.sum(ClientAssignment.used_bytes), 0),
                )
                .where(ClientAssignment.user_id.in_(list(user_ids)))
                .group_by(ClientAssignment.user_id)
            )
        ).all()
        return {r[0]: int(r[1] or 0) for r in rows}

    async def resync_user_usage_for_assignments(
        self, assignment_ids: Sequence[uuid.UUID]
    ) -> None:
        from app.domain.client_assignment import ClientAssignment
        from app.domain.user import User

        if not assignment_ids:
            return
        user_ids = (
            (
                await self.session.execute(
                    select(ClientAssignment.user_id)
                    .where(ClientAssignment.id.in_(list(assignment_ids)))
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        if not user_ids:
            return
        totals = await self.usage_sum_by_user(sorted(user_ids))
        for user_id in sorted(user_ids):
            await self.session.execute(
                update(User)
                .where(User.id == user_id)
                .values(users_data_usage=totals.get(user_id, 0))
                .execution_options(synchronize_session=False)
            )
        await self.session.flush()

    async def usage_for_users(
        self, user_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[int, int, bool]]:
        from app.domain.user import User

        # Report the ACCOUNT-level figures the panel actually enforces on:
        # used = User.users_data_usage (the maintained coefficient-adjusted total),
        # limit = User.data_limit_bytes, unlimited = data_limit_bytes IS NULL.
        # (Summing per-assignment traffic_limit_bytes produced an incoherent
        # "limit=X but unlimited=true" contract.)
        if not user_ids:
            return {}
        rows = (
            await self.session.execute(
                select(
                    User.id,
                    func.coalesce(User.users_data_usage, 0),
                    User.data_limit_bytes,
                ).where(User.id.in_(list(user_ids)))
            )
        ).all()
        return {
            r[0]: (int(r[1] or 0), int(r[2] or 0), r[2] is None) for r in rows
        }

    async def usage_by_node(self) -> dict[uuid.UUID, int]:
        from app.domain.client_assignment import ClientAssignment
        from app.domain.node import Node

        # Weight by the node's usage_coefficient so reported usage matches the
        # enforced counters (ClientAssignment.used_bytes is coefficient-adjusted
        # at ingest, while TrafficRecord.total_bytes is stored raw).
        weighted = func.coalesce(
            func.sum(TrafficRecord.total_bytes * func.coalesce(Node.usage_coefficient, 1.0)), 0
        )
        rows = (
            await self.session.execute(
                select(Node.id, weighted)
                .join(ClientAssignment, ClientAssignment.id == TrafficRecord.assignment_id)
                .join(Node, Node.id == ClientAssignment.node_id)
                .group_by(Node.id)
            )
        ).all()
        return {nid: int(total or 0) for nid, total in rows}

    async def usage_by_node_user(self, node_id: uuid.UUID) -> list[tuple[uuid.UUID, int]]:
        from app.domain.client_assignment import ClientAssignment
        from app.domain.node import Node

        weighted = func.coalesce(
            func.sum(TrafficRecord.total_bytes * func.coalesce(Node.usage_coefficient, 1.0)), 0
        )
        rows = (
            await self.session.execute(
                select(ClientAssignment.user_id, weighted)
                .join(ClientAssignment, ClientAssignment.id == TrafficRecord.assignment_id)
                .join(Node, Node.id == ClientAssignment.node_id)
                .where(ClientAssignment.node_id == node_id)
                .group_by(ClientAssignment.user_id)
                .order_by(weighted.desc())
            )
        ).all()
        return [(uid, int(total or 0)) for uid, total in rows]

    async def usage_by_user_node(self, user_id: uuid.UUID) -> list[tuple[uuid.UUID, str, int]]:
        from app.domain.client_assignment import ClientAssignment
        from app.domain.node import Node

        weighted = func.coalesce(
            func.sum(TrafficRecord.total_bytes * func.coalesce(Node.usage_coefficient, 1.0)), 0
        )
        rows = (
            await self.session.execute(
                select(Node.id, Node.name, weighted)
                .join(ClientAssignment, ClientAssignment.id == TrafficRecord.assignment_id)
                .join(Node, Node.id == ClientAssignment.node_id)
                .where(ClientAssignment.user_id == user_id)
                .group_by(Node.id, Node.name)
                .order_by(weighted.desc())
            )
        ).all()
        return [(nid, name, int(total or 0)) for nid, name, total in rows]

    async def _usage_hourly(
        self, field_name: str, field_value: uuid.UUID, since: datetime
    ) -> list[tuple[str, int, int]]:
        from app.domain.client_assignment import ClientAssignment

        rows = (
            await self.session.execute(
                select(
                    TrafficRecord.collected_at,
                    TrafficRecord.upload_bytes,
                    TrafficRecord.download_bytes,
                )
                .join(ClientAssignment, ClientAssignment.id == TrafficRecord.assignment_id)
                .where(
                    getattr(ClientAssignment, field_name) == field_value,
                    TrafficRecord.collected_at >= since,
                )
            )
        ).all()
        buckets: dict[datetime, list[int]] = {}
        for ts, up, down in rows:
            when = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
            hour = when.replace(minute=0, second=0, microsecond=0)
            slot = buckets.setdefault(hour, [0, 0])
            slot[0] += int(up or 0)
            slot[1] += int(down or 0)
        return [(k.isoformat(), v[0], v[1]) for k, v in sorted(buckets.items())]

    async def usage_hourly_for_node(
        self, node_id: uuid.UUID, since: datetime
    ) -> list[tuple[str, int, int]]:
        return await self._usage_hourly("node_id", node_id, since)

    async def usage_hourly_for_profile(
        self, profile_id: uuid.UUID, since: datetime
    ) -> list[tuple[str, int, int]]:
        return await self._usage_hourly("profile_id", profile_id, since)

    async def usage_total_for_profile(self, profile_id: uuid.UUID) -> int:
        from app.domain.client_assignment import ClientAssignment
        from app.domain.node import Node

        coeff = func.coalesce(Node.usage_coefficient, 1.0)
        total = (
            await self.session.execute(
                select(func.coalesce(func.sum(TrafficRecord.total_bytes * coeff), 0))
                .join(ClientAssignment, ClientAssignment.id == TrafficRecord.assignment_id)
                .join(Node, Node.id == ClientAssignment.node_id)
                .where(ClientAssignment.profile_id == profile_id)
            )
        ).scalar_one()
        return int(total or 0)

    async def usage_series_for_user(
        self, user_id: uuid.UUID, since: datetime
    ) -> list[tuple[str, int, int]]:
        from app.domain.client_assignment import ClientAssignment

        day = func.date(TrafficRecord.collected_at)
        rows = (
            await self.session.execute(
                select(
                    day,
                    func.coalesce(func.sum(TrafficRecord.upload_bytes), 0),
                    func.coalesce(func.sum(TrafficRecord.download_bytes), 0),
                )
                .join(ClientAssignment, ClientAssignment.id == TrafficRecord.assignment_id)
                .where(
                    ClientAssignment.user_id == user_id,
                    TrafficRecord.collected_at >= since,
                )
                .group_by(day)
                .order_by(day)
            )
        ).all()
        return [(str(d), int(up or 0), int(dn or 0)) for d, up, dn in rows]

    async def reactivate_disabled_assignments(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        from app.domain.client_assignment import AssignmentStatus, ClientAssignment

        node_rows = await self.session.execute(
            select(ClientAssignment.node_id).where(
                ClientAssignment.user_id == user_id,
                ClientAssignment.status == AssignmentStatus.LIMITED,
            )
        )
        node_ids = [nid for (nid,) in node_rows.all() if nid is not None]
        await self.session.execute(
            update(ClientAssignment)
            .where(
                ClientAssignment.user_id == user_id,
                ClientAssignment.status == AssignmentStatus.LIMITED,
            )
            .values(status=AssignmentStatus.ACTIVE)
            .execution_options(synchronize_session=False)
        )
        return node_ids

    async def reset_for_user(self, user_id: uuid.UUID) -> int:
        from app.domain.client_assignment import ClientAssignment

        ids = (
            (
                await self.session.execute(
                    select(ClientAssignment.id).where(ClientAssignment.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        if not ids:
            return 0
        await self.session.execute(
            delete(TrafficRecord).where(TrafficRecord.assignment_id.in_(ids))
        )
        await self.session.execute(
            update(ClientAssignment).where(ClientAssignment.id.in_(ids)).values(used_bytes=0)
        )
        return len(ids)
