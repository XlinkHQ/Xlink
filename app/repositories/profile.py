from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.domain.profile import Profile
from app.providers.base.models import ProviderKind
from app.repositories.base import BaseRepository


def _conflict_from_integrity(exc: IntegrityError) -> ConflictError:
    detail = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
    if "uq_profiles_slug" in detail or "profiles.slug" in detail or "slug" in detail:
        return ConflictError("Profile slug already exists.", code="slug_taken")
    return ConflictError("Profile already exists.", code="profile_conflict")


class ProfileRepository(BaseRepository[Profile]):
    model = Profile

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_slug(self, slug: str) -> Profile | None:
        return await self.get_by(slug=slug)

    async def create_profile(self, profile: Profile) -> Profile:
        try:
            async with self.session.begin_nested():
                self.session.add(profile)
                await self.session.flush()
        except IntegrityError as exc:
            raise _conflict_from_integrity(exc) from exc
        return profile

    async def save(self, profile: Profile) -> Profile:
        await self.session.flush()
        await self.session.refresh(profile)
        return profile

    async def list_keyset(
        self,
        *,
        limit: int,
        cursor: tuple[datetime, uuid.UUID] | None = None,
        provider_kind: ProviderKind | None = None,
        node_id: uuid.UUID | None = None,
        is_active: bool | None = None,
    ) -> Sequence[Profile]:
        stmt = select(Profile)
        if provider_kind is not None:
            stmt = stmt.where(Profile.provider_kind == provider_kind)
        if node_id is not None:
            stmt = stmt.where(Profile.node_id == node_id)
        if is_active is not None:
            stmt = stmt.where(Profile.is_active == is_active)
        if cursor is not None:
            cursor_created_at, cursor_id = cursor
            stmt = stmt.where(
                tuple_(Profile.created_at, Profile.id) < tuple_(cursor_created_at, cursor_id)
            )
        stmt = stmt.order_by(Profile.created_at.desc(), Profile.id.desc()).limit(limit)
        return (await self.session.execute(stmt)).scalars().all()
