from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.domain.group import Group, group_profiles
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

    async def set_profiles(self, group_id: uuid.UUID, profile_ids: Iterable[uuid.UUID]) -> None:
        """Replace a group's profile membership in the join table. Indexed
        delete-then-insert instead of rewriting a JSON blob."""
        await self.session.execute(
            delete(group_profiles).where(group_profiles.c.group_id == group_id)
        )
        rows = [{"group_id": group_id, "profile_id": pid} for pid in dict.fromkeys(profile_ids)]
        if rows:
            await self.session.execute(insert(group_profiles), rows)

    async def remove_profile_everywhere(self, profile_id: uuid.UUID) -> Sequence[uuid.UUID]:
        """Drop a profile from every group that contains it, returning the
        affected group ids. Replaces the full-table JSON scan on profile delete."""
        affected = (
            (
                await self.session.execute(
                    select(group_profiles.c.group_id).where(
                        group_profiles.c.profile_id == profile_id
                    )
                )
            )
            .scalars()
            .all()
        )
        if affected:
            await self.session.execute(
                delete(group_profiles).where(group_profiles.c.profile_id == profile_id)
            )
        return affected

    async def profile_ids_for_groups(self, group_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
        """Union of profile ids across the given groups — one indexed query
        instead of loading every group and unioning JSON in Python."""
        ids = list(group_ids)
        if not ids:
            return set()
        rows = await self.session.execute(
            select(group_profiles.c.profile_id).where(group_profiles.c.group_id.in_(ids)).distinct()
        )
        return set(rows.scalars().all())
