from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.domain.user import User, UserRole
from app.repositories.base import BaseRepository
from app.repositories.conflicts import conflict_from_integrity


def _conflict_from_integrity(exc: IntegrityError) -> ConflictError:
    return conflict_from_integrity(
        exc,
        [
            (
                ("uq_users_email", "users.email", "email"),
                "Email already registered.",
                "email_taken",
            ),
            (
                ("uq_users_username", "users.username", "username"),
                "Username already taken.",
                "username_taken",
            ),
        ],
        "User already exists.",
        "user_conflict",
    )


class UserRepository(BaseRepository[User]):
    model = User

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_username(self, username: str) -> User | None:
        return await self.get_by(username=username)

    async def get_by_identifier(self, identifier: str) -> User | None:
        ident = identifier.strip()
        stmt = (
            select(User)
            .where(
                or_(User.email == ident.lower(), User.username == ident),
                User.removed.is_(False),
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create_user(self, user: User) -> User:
        try:
            async with self.session.begin_nested():
                self.session.add(user)
                await self.session.flush()
        except IntegrityError as exc:
            raise _conflict_from_integrity(exc) from exc
        return user

    def _filter_conditions(
        self,
        role: UserRole | None,
        is_active: bool | None,
        include_removed: bool = False,
        owner_id: uuid.UUID | None = None,
    ) -> list[Any]:

        conditions = [] if include_removed else [User.removed.is_(False)]
        if role is not None:
            conditions.append(User.role == role)
        if is_active is not None:
            conditions.append(User.is_active == is_active)
        if owner_id is not None:
            conditions.append(User.owner_id == owner_id)
        return conditions

    async def list_paginated(
        self,
        *,
        offset: int,
        limit: int,
        role: UserRole | None = None,
        is_active: bool | None = None,
        include_removed: bool = False,
        owner_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[User], int]:
        conditions = self._filter_conditions(role, is_active, include_removed, owner_id)

        base = select(User)
        count_stmt = select(func.count()).select_from(User)
        for cond in conditions:
            base = base.where(cond)
            count_stmt = count_stmt.where(cond)

        total = int(await self.session.scalar(count_stmt) or 0)
        page_stmt = (
            base.order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(limit)
        )
        rows = (await self.session.execute(page_stmt)).scalars().all()
        return rows, total

    async def list_keyset(
        self,
        *,
        limit: int,
        cursor: tuple[datetime, uuid.UUID] | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
        include_removed: bool = False,
        owner_id: uuid.UUID | None = None,
    ) -> Sequence[User]:
        stmt = select(User)
        for cond in self._filter_conditions(role, is_active, include_removed, owner_id):
            stmt = stmt.where(cond)

        if cursor is not None:
            cursor_created_at, cursor_id = cursor
            stmt = stmt.where(
                tuple_(User.created_at, User.id) < tuple_(cursor_created_at, cursor_id)
            )

        stmt = stmt.order_by(User.created_at.desc(), User.id.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return rows
