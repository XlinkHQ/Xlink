from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.domain import (
    CommandStatus,
    NodeCommand,
    NodeDriftReport,
    NodeProviderHealth,
)


class NodeCommandRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, command: NodeCommand) -> NodeCommand:
        self.session.add(command)
        await self.session.flush()
        return command

    async def get(self, command_id: uuid.UUID) -> NodeCommand | None:
        return await self.session.get(NodeCommand, command_id)

    async def pending_for_node(self, node_id: uuid.UUID, *, limit: int) -> Sequence[NodeCommand]:
        stmt = (
            select(NodeCommand)
            .where(
                NodeCommand.node_id == node_id,
                NodeCommand.status == CommandStatus.PENDING,
            )
            .order_by(NodeCommand.created_at.asc(), NodeCommand.id.asc())
            .limit(max(1, limit))
            .with_for_update(skip_locked=True)
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def lease(
        self,
        node_id: uuid.UUID,
        *,
        lease_token: str,
        leased_at: datetime,
        lease_expires_at: datetime,
        limit: int,
    ) -> Sequence[NodeCommand]:
        commands = await self.pending_for_node(node_id, limit=limit)
        for command in commands:
            command.status = CommandStatus.LEASED
            command.lease_token = lease_token
            command.leased_at = leased_at
            command.lease_expires_at = lease_expires_at
            # lease_count bounds runaway re-leasing (crash/lost-report); attempts
            # counts real executions and is bumped only on report_result.
            command.lease_count += 1
        await self.session.flush()
        return commands

    async def complete(
        self,
        command: NodeCommand,
        *,
        success: bool,
        result: dict,
        completed_at: datetime,
    ) -> NodeCommand:
        command.status = CommandStatus.SUCCEEDED if success else CommandStatus.FAILED
        command.result = dict(result)
        command.completed_at = completed_at
        command.lease_token = None
        command.attempts += 1
        await self.session.flush()
        return command

    async def expire_leases(self, now: datetime) -> int:
        stmt = (
            update(NodeCommand)
            .where(
                NodeCommand.status == CommandStatus.LEASED,
                NodeCommand.lease_expires_at.is_not(None),
                NodeCommand.lease_expires_at < now,
                NodeCommand.lease_count < NodeCommand.max_attempts,
            )
            .values(status=CommandStatus.PENDING, lease_token=None)
        )
        result = await self.session.execute(stmt)
        exhausted = (
            update(NodeCommand)
            .where(
                NodeCommand.status == CommandStatus.LEASED,
                NodeCommand.lease_expires_at.is_not(None),
                NodeCommand.lease_expires_at < now,
                NodeCommand.lease_count >= NodeCommand.max_attempts,
            )
            .values(status=CommandStatus.EXPIRED, lease_token=None)
        )
        await self.session.execute(exhausted)
        return result.rowcount or 0

    async def has_open_kind(self, node_id: uuid.UUID, kind) -> bool:
        stmt = (
            select(NodeCommand.id)
            .where(
                NodeCommand.node_id == node_id,
                NodeCommand.kind == kind,
                NodeCommand.status.in_([CommandStatus.PENDING, CommandStatus.LEASED]),
            )
            .limit(1)
            .with_for_update()
        )
        return (await self.session.execute(stmt)).first() is not None


class NodeDriftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    _KEEP_PER_NODE = 20

    async def add(self, report: NodeDriftReport) -> NodeDriftReport:
        self.session.add(report)
        await self.session.flush()
        keep = (
            select(NodeDriftReport.id)
            .where(NodeDriftReport.node_id == report.node_id)
            .order_by(NodeDriftReport.detected_at.desc(), NodeDriftReport.id.desc())
            .limit(self._KEEP_PER_NODE)
        )
        await self.session.execute(
            delete(NodeDriftReport)
            .where(
                NodeDriftReport.node_id == report.node_id,
                NodeDriftReport.id.notin_(keep.scalar_subquery()),
            )
            .execution_options(synchronize_session=False)
        )
        return report

    async def latest_for_node(self, node_id: uuid.UUID) -> NodeDriftReport | None:
        stmt = (
            select(NodeDriftReport)
            .where(NodeDriftReport.node_id == node_id)
            .order_by(NodeDriftReport.detected_at.desc(), NodeDriftReport.id.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()


class NodeProviderHealthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_all(self, records: Sequence[NodeProviderHealth]) -> int:
        if not records:
            return 0
        self.session.add_all(list(records))
        await self.session.flush()
        return len(records)

    async def latest_for_node(self, node_id: uuid.UUID) -> Sequence[NodeProviderHealth]:
        # One row per provider — the most recent check. Without DISTINCT ON the
        # query returns every historical row, so the UI shows duplicate cores.
        # Latest row per provider. DISTINCT ON is Postgres-only, so order by
        # (provider, checked_at desc) and keep the first per provider in Python —
        # portable across Postgres and the sqlite test backend.
        stmt = (
            select(NodeProviderHealth)
            .where(NodeProviderHealth.node_id == node_id)
            .order_by(
                NodeProviderHealth.provider_name,
                NodeProviderHealth.checked_at.desc(),
            )
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        latest: dict[str, NodeProviderHealth] = {}
        for row in rows:
            latest.setdefault(row.provider_name, row)
        return list(latest.values())
