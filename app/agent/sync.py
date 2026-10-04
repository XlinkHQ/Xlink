from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import AssignmentSyncItem, RetryPolicy, SyncBatch, SyncCursor
from app.domain.client_assignment import ClientAssignment
from app.domain.profile import Profile


class NodeSyncService:
    def __init__(self, session: AsyncSession, retry: RetryPolicy | None = None) -> None:
        self._session = session
        self._retry = retry or RetryPolicy()

    async def assignment_sync(
        self,
        node_id: uuid.UUID,
        *,
        cursor: SyncCursor | None = None,
        limit: int = 100,
    ) -> SyncBatch:
        fetch_limit = max(1, limit) + 1
        stmt = (
            select(ClientAssignment, Profile)
            .join(Profile, ClientAssignment.profile_id == Profile.id)
            .where(ClientAssignment.node_id == node_id)
        )
        if cursor is not None:
            stmt = stmt.where(
                tuple_(ClientAssignment.updated_at, ClientAssignment.id)
                > tuple_(cursor.updated_at, cursor.assignment_id)  # type: ignore[arg-type]  # SQLAlchemy coerces cursor values to bind params
            )
        stmt = stmt.order_by(ClientAssignment.updated_at.asc(), ClientAssignment.id.asc()).limit(
            fetch_limit
        )
        rows = (await self._session.execute(stmt)).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = tuple(self._sync_item(assignment, profile) for assignment, profile in rows)
        next_cursor = None
        if items:
            last = items[-1]
            next_cursor = SyncCursor(updated_at=last.updated_at, assignment_id=last.assignment_id)
        return SyncBatch(node_id=node_id, items=items, next_cursor=next_cursor, has_more=has_more)

    async def with_retry[T](self, operation: Callable[[], Awaitable[T]]) -> T:
        attempts = max(1, self._retry.max_attempts)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await operation()
            except Exception as exc:
                last_error = exc
                if attempt < attempts:
                    import asyncio

                    await asyncio.sleep(self._retry.delay_for(attempt))
        raise last_error

    def _sync_item(self, assignment: ClientAssignment, profile: Profile) -> AssignmentSyncItem:
        settings = {
            **profile.settings,
            "profile_slug": profile.slug,
            "protocol": profile.protocol,
        }
        return AssignmentSyncItem.build(
            assignment_id=assignment.id,
            user_id=assignment.user_id,
            profile_id=assignment.profile_id,
            provider_kind=assignment.provider_kind,
            provider_client_id=assignment.provider_client_id,
            status=assignment.status,
            version=assignment.version,
            updated_at=assignment.updated_at,
            settings=settings,
        )
