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

    async def latest(self, *, entity_type: str, entity_id) -> GitOpsRecord | None:
        stmt = (
            select(GitOpsRecord)
            .where(
                GitOpsRecord.entity_type == entity_type,
                GitOpsRecord.entity_id == entity_id,
            )
            .order_by(GitOpsRecord.created_at.desc(), GitOpsRecord.id.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()
