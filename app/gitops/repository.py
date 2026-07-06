from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.gitops import GitOpsAction, GitOpsRecord
from app.gitops.models import GitDiff, GitSnapshot


class GitOpsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        snapshot: GitSnapshot,
        diff: GitDiff,
        action: GitOpsAction,
        actor: str | None = None,
        message: str | None = None,
    ) -> GitOpsRecord:
        record = GitOpsRecord(
            entity_type=snapshot.entity_type,
            entity_id=snapshot.entity_id,
            action=action,
            actor=actor,
            message=message,
            snapshot=snapshot.data,
            diff={
                "added": diff.added,
                "changed": diff.changed,
                "removed": diff.removed,
            },
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_recent(self, *, limit: int = 100) -> list[GitOpsRecord]:
        stmt = (
            select(GitOpsRecord)
            .order_by(GitOpsRecord.created_at.desc(), GitOpsRecord.id.desc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars().all())

