from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.domain.group import Group
from app.repositories.base import BaseRepository
from app.repositories.conflicts import conflict_from_integrity


def _conflict_from_integrity(exc: IntegrityError) -> ConflictError:
    return conflict_from_integrity(
        exc,
        [
            (
                ("uq_groups_slug", "groups.slug", "slug"),
                "Group slug already exists.",
                "slug_taken",
            ),
        ],
        "Group already exists.",
        "group_conflict",
    )


class GroupRepository(BaseRepository[Group]):
    model = Group

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create_group(self, group: Group) -> Group:
        try:
            async with self.session.begin_nested():
                self.session.add(group)
                await self.session.flush()
        except IntegrityError as exc:
            raise _conflict_from_integrity(exc) from exc
        return group

    async def list_all(self) -> Sequence[Group]:
        result = await self.session.execute(select(Group).order_by(Group.created_at.desc()))
        return result.scalars().all()
