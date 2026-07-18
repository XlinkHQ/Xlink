from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.gitops import GitOpsAction, GitOpsRecord
from app.events.models import DomainEvent
from app.gitops.diff import DiffEngine
from app.gitops.models import GitDiff, GitSnapshot
from app.gitops.repository import GitOpsRepository
from app.gitops.snapshot import SnapshotBuilder


class GitOpsService:
    def __init__(self, session: AsyncSession) -> None:
        self._snapshots = SnapshotBuilder()
        self._diffs = DiffEngine()
        self._repository = GitOpsRepository(session)

    def snapshot(
        self,
        *,
        entity_type: str,
        entity_id,
        payload: Mapping[str, Any],
    ) -> GitSnapshot:
        return self._snapshots.capture(
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )

    def diff(self, before: GitSnapshot, after: GitSnapshot) -> GitDiff:
        return self._diffs.compare(before.data, after.data)

    async def list_recent(self, *, limit: int = 100) -> list[GitOpsRecord]:
        return await self._repository.list_recent(limit=limit)

    async def commit(
        self,
        *,
        before: GitSnapshot | None,
        after: GitSnapshot,
        actor: str | None = None,
        message: str | None = None,
    ) -> GitOpsRecord:
        diff = self._diffs.compare(before.data if before is not None else {}, after.data)
        return await self._repository.create(
            snapshot=after,
            diff=diff,
            action=GitOpsAction.COMMIT,
            actor=actor,
            message=message,
        )

    async def snapshot_event(self, event: DomainEvent) -> GitOpsRecord:
        snapshot = self.snapshot(
            entity_type=event.event_name,
            entity_id=event.event_id,
            payload={
                "event_id": event.event_id,
                "occurred_at": event.occurred_at,
                "correlation_id": event.correlation_id,
                "metadata": event.metadata,
            },
        )
        return await self._repository.create(
            snapshot=snapshot,
            diff=self._diffs.compare({}, snapshot.data),
            action=GitOpsAction.SNAPSHOT,
            message="domain event snapshot",
        )
