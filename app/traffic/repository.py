from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.traffic.models import TrafficHourly, TrafficRecord, TrafficRollupState
from app.traffic.schemas import TrafficTotals, TrafficUsage


def _hour_bucket_expr(dialect: str):
    """SQL expression truncating TrafficRecord.collected_at to the hour, portable
    across Postgres and SQLite. Postgres keeps a real timestamptz; SQLite has no
    date_trunc so we format to 'YYYY-MM-DD HH:00:00' text — which SQLAlchemy's
    DateTime type adapter reads back as a datetime on the way out."""
    if dialect == "sqlite":
        return func.strftime("%Y-%m-%d %H:00:00", TrafficRecord.collected_at)
    return func.date_trunc("hour", TrafficRecord.collected_at)


def _as_hour_datetime(value) -> datetime:
    """Normalise a hour-bucket value from the aggregation SELECT into a tz-aware
    UTC datetime truncated to the hour. Postgres date_trunc already yields a
    datetime; SQLite's strftime yields a 'YYYY-MM-DD HH:MM:SS' string which the
    DateTime column's bind would otherwise reject on re-insert."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.replace(minute=0, second=0, microsecond=0)


class TrafficRepository:
    # Minimum lifetime for the idempotency ledger (ProcessedBatch), in days.
    # Floors the ledger GC so a node offline up to this long cannot re-deliver a
    # WAL batch whose ledger row was already purged (→ double-count). MUST stay
    # comfortably ABOVE the agent's WAL age cap (XLINK_WAL_MAX_AGE_DAYS, default
    # 30d): the WAL can never hold a batch older than its cap, and the ledger
    # always remembers batches at least this long, so the windows never cross.
    _LEDGER_MIN_RETENTION_DAYS = 90

    def __init__(
        self, session: AsyncSession, *, reader_session: AsyncSession | None = None
    ) -> None:
        self.session = session
        # OPTIONAL replica session for pure, lag-tolerant analytics reads (the
        # SUM/series/by-node aggregations). None when no replica is configured →
        # these reads use the primary session, identical to before. NEVER used
        # for writes, ingest, rollup, or read-after-write-sensitive reads.
        self.reader = reader_session or session

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

    async def bulk_insert(self, rows: Sequence[dict]) -> tuple[dict[uuid.UUID, int], int]:
        """Insert rows, ignoring (assignment_id, collected_at) conflicts, and
        return (per-assignment SUM of total_bytes, number of rows) that were
        ACTUALLY inserted (via RETURNING).

        The caller applies these as usage deltas, NOT a delta derived from a
        pre-insert existing-keys snapshot: two concurrent batches carrying the
        same sample under different batch_ids both see the key absent in a
        snapshot, but ON CONFLICT lets only one row survive — RETURNING
        attributes each inserted row's bytes to exactly the one transaction that
        inserted it, so a sample is counted once. Summing the RETURNING bytes
        directly also sidesteps any timestamp round-trip mismatch between the
        Python-side input rows and the DB-stored collected_at."""
        if not rows:
            return {}, 0
        dialect = self.session.bind.dialect.name if self.session.bind else "postgresql"
        if dialect == "sqlite":
            stmt = sqlite_insert(TrafficRecord).values(list(rows))
            stmt = stmt.on_conflict_do_nothing(index_elements=["assignment_id", "collected_at"])
        else:
            stmt = pg_insert(TrafficRecord).values(list(rows))
            stmt = stmt.on_conflict_do_nothing(constraint="uq_traffic_records_assignment_collected")
        stmt = stmt.returning(TrafficRecord.assignment_id, TrafficRecord.total_bytes)
        result = await self.session.execute(stmt)
        deltas: dict[uuid.UUID, int] = {}
        inserted = 0
        for aid, total in result.all():
            deltas[aid] = deltas.get(aid, 0) + int(total or 0)
            inserted += 1
        await self.session.flush()
        return deltas, inserted

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

    async def _weighted_totals_stmt(self, since: datetime | None = None):
        from app.domain.client_assignment import ClientAssignment
        from app.domain.node import Node

        # Read from the rollup+raw union so all-time / since totals stay correct
        # even after raw rows older than the rollup have been purged (otherwise a
        # raw-only scan would silently undercount purged history). record_count
        # here counts SOURCE rows (rolled hour-buckets + raw samples), not raw
        # samples — a full raw sample count is no longer meaningful once rolled
        # buckets replace the samples that produced them.
        boundary = await self._read_boundary(reader=True)
        src = self._unified_usage_ts_cte(boundary)
        coeff = func.coalesce(Node.usage_coefficient, 1.0)
        stmt = (
            select(
                func.coalesce(func.sum(src.c.total_bytes * coeff), 0),
                func.coalesce(func.sum(src.c.upload_bytes * coeff), 0),
                func.coalesce(func.sum(src.c.download_bytes * coeff), 0),
                func.count(),
            )
            .select_from(src)
            .join(ClientAssignment, ClientAssignment.id == src.c.assignment_id)
            .join(Node, Node.id == ClientAssignment.node_id)
        )
        if since is not None:
            stmt = stmt.where(src.c.bucket_start >= since)
        return stmt

    def _unified_usage_ts_cte(self, boundary: datetime):
        """Like _unified_usage_cte but also carries a `bucket_start` time column
        (hour_bucket for rollup rows, collected_at for raw rows) so callers can
        apply a time filter across both sources."""
        rollup = select(
            TrafficHourly.assignment_id.label("assignment_id"),
            TrafficHourly.node_id.label("node_id"),
            TrafficHourly.hour_bucket.label("bucket_start"),
            TrafficHourly.upload_bytes.label("upload_bytes"),
            TrafficHourly.download_bytes.label("download_bytes"),
            TrafficHourly.total_bytes.label("total_bytes"),
        ).where(TrafficHourly.hour_bucket < boundary)
        raw = select(
            TrafficRecord.assignment_id.label("assignment_id"),
            TrafficRecord.node_id.label("node_id"),
            TrafficRecord.collected_at.label("bucket_start"),
            TrafficRecord.upload_bytes.label("upload_bytes"),
            TrafficRecord.download_bytes.label("download_bytes"),
            TrafficRecord.total_bytes.label("total_bytes"),
        ).where(TrafficRecord.collected_at >= boundary)
        return rollup.union_all(raw).subquery("usage_ts_src")

    async def totals(self) -> TrafficTotals:
        stmt = await self._weighted_totals_stmt()
        total, up, down, count = (await self.reader.execute(stmt)).one()
        return TrafficTotals(
            total_bytes=int(total),
            upload_bytes=int(up),
            download_bytes=int(down),
            record_count=int(count),
        )

    async def totals_since(self, since: datetime) -> TrafficTotals:
        stmt = await self._weighted_totals_stmt(since=since)
        total, up, down, count = (await self.reader.execute(stmt)).one()
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
        # re-delivered batch look brand-new → double-count.
        #
        # `cutoff` here is the RAW cutoff (min(raw_retention, rollup watermark)),
        # which collapses to a few hours once rollups run steadily — so a naive
        # "2×(now-cutoff)" ledger window can shrink to hours and stop protecting
        # against a long-offline node. Floor the ledger horizon at a fixed minimum
        # (_LEDGER_MIN_RETENTION_DAYS) so a node offline up to that many days can
        # never re-deliver a batch whose ledger row was already GC'd. The agent's
        # WAL age cap (XLINK_WAL_MAX_AGE_DAYS, default 30d) is kept well under this
        # floor, so the two windows can never cross.
        now = datetime.now(UTC)
        two_x_cutoff = cutoff - (now - cutoff)
        floor_cutoff = now - timedelta(days=self._LEDGER_MIN_RETENTION_DAYS)
        ledger_cutoff = min(two_x_cutoff, floor_cutoff)
        await self.session.execute(
            delete(ProcessedBatch).where(ProcessedBatch.created_at < ledger_cutoff)
        )
        await self.session.commit()
        return deleted

    async def count(self) -> int:
        return int(await self.session.scalar(select(func.count()).select_from(TrafficRecord)) or 0)

    async def hourly_count(self) -> int:
        return int(await self.session.scalar(select(func.count()).select_from(TrafficHourly)) or 0)

    # ------------------------------------------------------------------
    # Hourly rollup / compaction
    # ------------------------------------------------------------------
    async def get_rollup_watermark(self) -> datetime | None:
        state = await self.session.get(TrafficRollupState, 1)
        wm = state.hourly_watermark if state is not None else None
        if wm is not None and wm.tzinfo is None:
            wm = wm.replace(tzinfo=UTC)
        return wm

    async def set_rollup_watermark(self, watermark: datetime) -> None:
        state = await self.session.get(TrafficRollupState, 1)
        if state is None:
            state = TrafficRollupState(id=1, hourly_watermark=watermark)
            self.session.add(state)
        else:
            state.hourly_watermark = watermark
        await self.session.flush()

    async def rollup_hourly(self, *, floor_hour: datetime, since: datetime | None) -> int:
        """Aggregate raw traffic_records for CLOSED hour buckets into traffic_hourly.

        Only buckets strictly before `floor_hour` (the current hour) are rolled up
        — the in-progress hour is still receiving samples and would produce a
        partial sum. `since` limits the recomputation to buckets at/after the
        watermark so a steady-state run only touches recent buckets.

        Idempotency: each bucket is upserted with the freshly recomputed SUM
        (ON CONFLICT ... DO UPDATE SET col = excluded.col), NOT an increment, so
        re-running over the same window yields the same totals and never
        double-counts. Returns the number of (assignment, bucket) rows written.
        """
        dialect = self.session.bind.dialect.name if self.session.bind else "postgresql"
        bucket = _hour_bucket_expr(dialect)
        conditions = [TrafficRecord.collected_at < floor_hour]
        if since is not None:
            conditions.append(TrafficRecord.collected_at >= since)
        agg = (
            select(
                TrafficRecord.assignment_id.label("assignment_id"),
                func.min(TrafficRecord.node_id).label("node_id"),
                bucket.label("hour_bucket"),
                func.coalesce(func.sum(TrafficRecord.upload_bytes), 0).label("upload_bytes"),
                func.coalesce(func.sum(TrafficRecord.download_bytes), 0).label("download_bytes"),
                func.coalesce(func.sum(TrafficRecord.total_bytes), 0).label("total_bytes"),
            )
            .where(*conditions)
            .group_by(TrafficRecord.assignment_id, bucket)
        )
        rows = (await self.session.execute(agg)).all()
        if not rows:
            return 0
        payload = [
            {
                "assignment_id": r.assignment_id,
                "node_id": r.node_id,
                "hour_bucket": _as_hour_datetime(r.hour_bucket),
                "upload_bytes": int(r.upload_bytes or 0),
                "download_bytes": int(r.download_bytes or 0),
                "total_bytes": int(r.total_bytes or 0),
            }
            for r in rows
        ]
        if dialect == "sqlite":
            stmt = sqlite_insert(TrafficHourly).values(payload)
            stmt = stmt.on_conflict_do_update(
                index_elements=["assignment_id", "hour_bucket"],
                set_={
                    "node_id": stmt.excluded.node_id,
                    "upload_bytes": stmt.excluded.upload_bytes,
                    "download_bytes": stmt.excluded.download_bytes,
                    "total_bytes": stmt.excluded.total_bytes,
                },
            )
        else:
            stmt = pg_insert(TrafficHourly).values(payload)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_traffic_hourly_assignment_bucket",
                set_={
                    "node_id": stmt.excluded.node_id,
                    "upload_bytes": stmt.excluded.upload_bytes,
                    "download_bytes": stmt.excluded.download_bytes,
                    "total_bytes": stmt.excluded.total_bytes,
                },
            )
        await self.session.execute(stmt)
        await self.session.flush()
        return len(payload)

    async def delete_hourly_before(self, cutoff: datetime, *, batch: int = 10000) -> int:
        deleted = 0
        while True:
            sub = (
                select(TrafficHourly.id).where(TrafficHourly.hour_bucket < cutoff).limit(batch)
            )
            stmt = delete(TrafficHourly).where(TrafficHourly.id.in_(sub.scalar_subquery()))
            result = await self.session.execute(stmt)
            n = result.rowcount or 0
            deleted += n
            await self.session.commit()
            if n < batch:
                break
            await asyncio.sleep(0)
        return deleted

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

    # ------------------------------------------------------------------
    # Rollup-aware analytics reads
    #
    # The raw/rollup boundary is the rollup watermark: the first hour bucket the
    # rollup job has NOT yet aggregated. Everything strictly before it lives in
    # traffic_hourly (closed buckets); everything at/after it is still only in
    # traffic_records (the current + not-yet-rolled window). Reads below UNION a
    # rollup slice (traffic_hourly, hour_bucket < boundary) with a raw slice
    # (traffic_records, collected_at >= boundary) so the two never overlap and
    # never double-count, regardless of when the rollup job last ran. If the
    # rollup has never run (watermark NULL) the boundary is the epoch so the
    # rollup slice is empty and EVERYTHING is read from raw — behaviour is then
    # identical to the pre-rollup code.
    # ------------------------------------------------------------------
    _EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

    async def _read_boundary(self, *, reader: bool = False) -> datetime:
        session = self.reader if reader else self.session
        state = await session.get(TrafficRollupState, 1)
        wm = state.hourly_watermark if state is not None else None
        if wm is not None and wm.tzinfo is None:
            wm = wm.replace(tzinfo=UTC)
        return wm if wm is not None else self._EPOCH

    def _unified_usage_cte(self, boundary: datetime):
        """A UNION ALL of (assignment_id, node_id, upload, download, total) rows
        from the rollup (closed buckets) and raw (open window), as a subquery the
        callers join to ClientAssignment/Node and aggregate over — identical to
        how they aggregated raw records before, just over both sources."""
        rollup = select(
            TrafficHourly.assignment_id.label("assignment_id"),
            TrafficHourly.node_id.label("node_id"),
            TrafficHourly.upload_bytes.label("upload_bytes"),
            TrafficHourly.download_bytes.label("download_bytes"),
            TrafficHourly.total_bytes.label("total_bytes"),
        ).where(TrafficHourly.hour_bucket < boundary)
        raw = select(
            TrafficRecord.assignment_id.label("assignment_id"),
            TrafficRecord.node_id.label("node_id"),
            TrafficRecord.upload_bytes.label("upload_bytes"),
            TrafficRecord.download_bytes.label("download_bytes"),
            TrafficRecord.total_bytes.label("total_bytes"),
        ).where(TrafficRecord.collected_at >= boundary)
        return rollup.union_all(raw).subquery("usage_src")

    async def usage_by_node(self) -> dict[uuid.UUID, int]:
        from app.domain.client_assignment import ClientAssignment
        from app.domain.node import Node

        # Weight by the node's usage_coefficient so reported usage matches the
        # enforced counters (ClientAssignment.used_bytes is coefficient-adjusted
        # at ingest, while stored bytes are raw). Reads from the rollup+raw union.
        src = self._unified_usage_cte(await self._read_boundary(reader=True))
        weighted = func.coalesce(
            func.sum(src.c.total_bytes * func.coalesce(Node.usage_coefficient, 1.0)), 0
        )
        rows = (
            await self.reader.execute(
                select(Node.id, weighted)
                .select_from(src)
                .join(ClientAssignment, ClientAssignment.id == src.c.assignment_id)
                .join(Node, Node.id == ClientAssignment.node_id)
                .group_by(Node.id)
            )
        ).all()
        return {nid: int(total or 0) for nid, total in rows}

    async def usage_by_node_user(self, node_id: uuid.UUID) -> list[tuple[uuid.UUID, int]]:
        from app.domain.client_assignment import ClientAssignment
        from app.domain.node import Node

        src = self._unified_usage_cte(await self._read_boundary(reader=True))
        weighted = func.coalesce(
            func.sum(src.c.total_bytes * func.coalesce(Node.usage_coefficient, 1.0)), 0
        )
        rows = (
            await self.reader.execute(
                select(ClientAssignment.user_id, weighted)
                .select_from(src)
                .join(ClientAssignment, ClientAssignment.id == src.c.assignment_id)
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

        src = self._unified_usage_cte(await self._read_boundary(reader=True))
        weighted = func.coalesce(
            func.sum(src.c.total_bytes * func.coalesce(Node.usage_coefficient, 1.0)), 0
        )
        rows = (
            await self.reader.execute(
                select(Node.id, Node.name, weighted)
                .select_from(src)
                .join(ClientAssignment, ClientAssignment.id == src.c.assignment_id)
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

        # Hourly series: closed hours come pre-bucketed from traffic_hourly, the
        # current/not-yet-rolled window from raw records bucketed in Python. The
        # boundary keeps the two disjoint so no hour is counted from both.
        boundary = await self._read_boundary(reader=True)
        buckets: dict[datetime, list[int]] = {}

        hourly_rows = (
            await self.reader.execute(
                select(
                    TrafficHourly.hour_bucket,
                    TrafficHourly.upload_bytes,
                    TrafficHourly.download_bytes,
                )
                .join(ClientAssignment, ClientAssignment.id == TrafficHourly.assignment_id)
                .where(
                    getattr(ClientAssignment, field_name) == field_value,
                    TrafficHourly.hour_bucket >= since,
                    TrafficHourly.hour_bucket < boundary,
                )
            )
        ).all()
        for ts, up, down in hourly_rows:
            when = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
            hour = when.replace(minute=0, second=0, microsecond=0)
            slot = buckets.setdefault(hour, [0, 0])
            slot[0] += int(up or 0)
            slot[1] += int(down or 0)

        raw_rows = (
            await self.reader.execute(
                select(
                    TrafficRecord.collected_at,
                    TrafficRecord.upload_bytes,
                    TrafficRecord.download_bytes,
                )
                .join(ClientAssignment, ClientAssignment.id == TrafficRecord.assignment_id)
                .where(
                    getattr(ClientAssignment, field_name) == field_value,
                    TrafficRecord.collected_at >= since,
                    TrafficRecord.collected_at >= boundary,
                )
            )
        ).all()
        for ts, up, down in raw_rows:
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

        src = self._unified_usage_cte(await self._read_boundary(reader=True))
        coeff = func.coalesce(Node.usage_coefficient, 1.0)
        total = (
            await self.reader.execute(
                select(func.coalesce(func.sum(src.c.total_bytes * coeff), 0))
                .select_from(src)
                .join(ClientAssignment, ClientAssignment.id == src.c.assignment_id)
                .join(Node, Node.id == ClientAssignment.node_id)
                .where(ClientAssignment.profile_id == profile_id)
            )
        ).scalar_one()
        return int(total or 0)

    async def usage_series_for_user(
        self, user_id: uuid.UUID, since: datetime
    ) -> list[tuple[str, int, int]]:
        from app.domain.client_assignment import ClientAssignment

        # Daily series derived by grouping the hourly rollup (closed hours) plus
        # the raw open window by calendar day. The boundary keeps the two
        # disjoint. Day grouping is done in Python so the two source shapes
        # (hour_bucket vs collected_at) fold into the same day key uniformly.
        boundary = await self._read_boundary(reader=True)
        days: dict[str, list[int]] = {}

        def _add(ts: datetime, up: int, dn: int) -> None:
            when = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
            key = when.date().isoformat()
            slot = days.setdefault(key, [0, 0])
            slot[0] += int(up or 0)
            slot[1] += int(dn or 0)

        hourly_rows = (
            await self.reader.execute(
                select(
                    TrafficHourly.hour_bucket,
                    TrafficHourly.upload_bytes,
                    TrafficHourly.download_bytes,
                )
                .join(ClientAssignment, ClientAssignment.id == TrafficHourly.assignment_id)
                .where(
                    ClientAssignment.user_id == user_id,
                    TrafficHourly.hour_bucket >= since,
                    TrafficHourly.hour_bucket < boundary,
                )
            )
        ).all()
        for ts, up, dn in hourly_rows:
            _add(ts, up, dn)

        raw_rows = (
            await self.reader.execute(
                select(
                    TrafficRecord.collected_at,
                    TrafficRecord.upload_bytes,
                    TrafficRecord.download_bytes,
                )
                .join(ClientAssignment, ClientAssignment.id == TrafficRecord.assignment_id)
                .where(
                    ClientAssignment.user_id == user_id,
                    TrafficRecord.collected_at >= since,
                    TrafficRecord.collected_at >= boundary,
                )
            )
        ).all()
        for ts, up, dn in raw_rows:
            _add(ts, up, dn)

        return [(d, days[d][0], days[d][1]) for d in sorted(days)]

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
