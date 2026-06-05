from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.client_assignment import ClientAssignment
from app.domain.node import Node
from app.domain.profile import Profile
from app.subscription.models import SubscriptionSource


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_assignment_source(self, assignment_id: uuid.UUID) -> SubscriptionSource | None:
        rows = await self._sources(ClientAssignment.id == assignment_id)
        return rows[0] if rows else None

    async def list_assignment_sources(
        self, assignment_id: uuid.UUID
    ) -> tuple[SubscriptionSource, ...]:
        return await self._sources(ClientAssignment.id == assignment_id)

    async def list_profile_sources(self, profile_id: uuid.UUID) -> tuple[SubscriptionSource, ...]:
        return await self._sources(ClientAssignment.profile_id == profile_id)

    async def list_user_sources(self, user_id: uuid.UUID) -> tuple[SubscriptionSource, ...]:
        return await self._sources(ClientAssignment.user_id == user_id)

    async def _sources(self, *conditions) -> tuple[SubscriptionSource, ...]:
        stmt = (
            select(ClientAssignment, Profile, Node)
            .join(Profile, ClientAssignment.profile_id == Profile.id)
            .join(Node, ClientAssignment.node_id == Node.id)
            .where(*conditions)
            .order_by(ClientAssignment.created_at.desc(), ClientAssignment.id.desc())
        )
        result = await self._session.execute(stmt)
        return tuple(
            SubscriptionSource(assignment=assignment, profile=profile, node=node)
            for assignment, profile, node in result.all()
        )
