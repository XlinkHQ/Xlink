from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.providers.base.models import ProviderKind
from app.repositories.base import BaseRepository
from app.repositories.conflicts import conflict_from_integrity


def _conflict_from_integrity(exc: IntegrityError) -> ConflictError:
    return conflict_from_integrity(
        exc,
        [
            (
                ("uq_client_assignments_triplet",),
                "Assignment already exists for this user, profile and node.",
                "assignment_exists",
            ),
        ],
        "Assignment already exists.",
        "assignment_conflict",
    )


class ClientAssignmentRepository(BaseRepository[ClientAssignment]):
    model = ClientAssignment

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def triplet_exists(
        self, user_id: uuid.UUID, profile_id: uuid.UUID, node_id: uuid.UUID
    ) -> bool:
        return await self.exists(user_id=user_id, profile_id=profile_id, node_id=node_id)

    async def list_by_group(self, group_id: uuid.UUID) -> Sequence[ClientAssignment]:
        result = await self.session.execute(
            select(ClientAssignment).where(ClientAssignment.group_id == group_id)
        )
        return result.scalars().all()

    async def add_pending(self, assignment: ClientAssignment) -> ClientAssignment:
        try:
            async with self.session.begin_nested():
                self.session.add(assignment)
                await self.session.flush()
        except IntegrityError as exc:
            raise _conflict_from_integrity(exc) from exc
        return assignment

    async def save(self, assignment: ClientAssignment) -> ClientAssignment:
        await self.session.flush()
        await self.session.refresh(assignment)
        return assignment

    async def remove(self, assignment: ClientAssignment) -> None:
        await self.session.delete(assignment)
        await self.session.flush()

    async def list_keyset(
        self,
        *,
        limit: int,
        cursor: tuple[datetime, uuid.UUID] | None = None,
        user_id: uuid.UUID | None = None,
        owner_id: uuid.UUID | None = None,
        profile_id: uuid.UUID | None = None,
        node_id: uuid.UUID | None = None,
        provider_kind: ProviderKind | None = None,
        status: AssignmentStatus | None = None,
    ) -> Sequence[ClientAssignment]:
        stmt = select(ClientAssignment)
        if user_id is not None:
            stmt = stmt.where(ClientAssignment.user_id == user_id)
        if owner_id is not None:
            from app.domain.user import User

            stmt = stmt.where(
                ClientAssignment.user_id.in_(select(User.id).where(User.owner_id == owner_id))
            )
        if profile_id is not None:
            stmt = stmt.where(ClientAssignment.profile_id == profile_id)
        if node_id is not None:
            stmt = stmt.where(ClientAssignment.node_id == node_id)
        if provider_kind is not None:
            stmt = stmt.where(ClientAssignment.provider_kind == provider_kind)
        if status is not None:
            stmt = stmt.where(ClientAssignment.status == status)
        if cursor is not None:
            cursor_created_at, cursor_id = cursor
            stmt = stmt.where(
                tuple_(ClientAssignment.created_at, ClientAssignment.id)
                < tuple_(cursor_created_at, cursor_id)
            )
        stmt = stmt.order_by(ClientAssignment.created_at.desc(), ClientAssignment.id.desc()).limit(
            limit
        )
        return (await self.session.execute(stmt)).scalars().all()
