from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.core.exceptions import ConflictError, NotFoundError
from app.domain.group import Group
from app.repositories.group import GroupRepository
from app.schemas.group import GroupCreate, GroupUpdate
from app.services._shared import save_or_conflict


class GroupService:
    def __init__(self, repo: GroupRepository) -> None:
        self._repo = repo

    async def create(self, data: GroupCreate) -> Group:
        group = Group(name=data.name, slug=data.slug)
        group = await self._repo.create_group(group)
        await self._repo.set_profiles(group.id, data.profile_ids)
        await self._repo.session.refresh(group, attribute_names=["profiles"])
        return group

    async def get(self, group_id: uuid.UUID) -> Group:
        group = await self._repo.get(group_id)
        if group is None:
            raise NotFoundError("Group not found.", code="group_not_found")
        return group

    async def list_all(self) -> Sequence[Group]:
        return await self._repo.list_all()

    async def update(self, group_id: uuid.UUID, data: GroupUpdate) -> Group:
        group = await self.get(group_id)
        if data.expected_version is not None and data.expected_version != group.version:
            raise ConflictError("Group was modified concurrently.", code="version_conflict")
        if data.name is not None:
            group.name = data.name
        if data.profile_ids is not None:
            await self._repo.set_profiles(group.id, data.profile_ids)
            group.name = group.name

        async def _save(g: Group) -> Group:
            await self._repo.session.flush()
            await self._repo.session.refresh(g, attribute_names=["profiles"])
            return g

        return await save_or_conflict(_save, group, "Group")

    async def delete(self, group_id: uuid.UUID) -> None:
        group = await self.get(group_id)
        await self._repo.delete(group)
