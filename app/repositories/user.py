from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, ClassVar

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
        search: str | None = None,
    ) -> list[Any]:

        conditions = [] if include_removed else [User.removed.is_(False)]
        if role is not None:
            conditions.append(User.role == role)
        if is_active is not None:
            conditions.append(User.is_active == is_active)
        if owner_id is not None:
            conditions.append(User.owner_id == owner_id)
        if search:
            needle = f"%{search.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(User.username).like(needle),
                    func.lower(func.coalesce(User.email, "")).like(needle),
                )
            )
        return conditions

    _SORTS: ClassVar[dict[str, tuple[Any, Any]]] = {
        "newest": (User.created_at.desc(), User.id.desc()),
        "oldest": (User.created_at.asc(), User.id.asc()),
        "name": (User.username.asc(), User.id.asc()),
        "traffic": (User.users_data_usage.desc(), User.id.desc()),
        "expiring": (User.expire_at.asc().nulls_last(), User.id.asc()),
    }

    # Keyset spec per sort: (column, is_descending, attribute-name-for-cursor-value).
    # `expiring` is nullable → handled with a null-aware clause below.
    _KEYSET: ClassVar[dict[str, tuple[Any, bool, str]]] = {
        "newest": (User.created_at, True, "created_at"),
        "oldest": (User.created_at, False, "created_at"),
        "name": (User.username, False, "username"),
        "traffic": (User.users_data_usage, True, "users_data_usage"),
        "expiring": (User.expire_at, False, "expire_at"),
    }

    def _order_by(self, sort: str | None):
        return self._SORTS.get(sort or "newest", self._SORTS["newest"])

    async def list_paginated(
        self,
        *,
        offset: int,
        limit: int,
        role: UserRole | None = None,
        is_active: bool | None = None,
        include_removed: bool = False,
        owner_id: uuid.UUID | None = None,
        search: str | None = None,
        sort: str | None = None,
    ) -> tuple[Sequence[User], int]:
        conditions = self._filter_conditions(role, is_active, include_removed, owner_id, search)

        base = select(User)
        count_stmt = select(func.count()).select_from(User)
        for cond in conditions:
            base = base.where(cond)
            count_stmt = count_stmt.where(cond)

        total = int(await self.session.scalar(count_stmt) or 0)
        page_stmt = base.order_by(*self._order_by(sort)).offset(offset).limit(limit)
        rows = (await self.session.execute(page_stmt)).scalars().all()
        return rows, total

    async def list_keyset(
        self,
        *,
        limit: int,
        cursor: tuple[object, uuid.UUID] | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
        include_removed: bool = False,
        owner_id: uuid.UUID | None = None,
        search: str | None = None,
        sort: str | None = None,
    ) -> Sequence[User]:
        from sqlalchemy import and_

        stmt = select(User)
        for cond in self._filter_conditions(role, is_active, include_removed, owner_id, search):
            stmt = stmt.where(cond)

        col, desc, _ = self._KEYSET.get(sort or "newest", self._KEYSET["newest"])
        if cursor is not None:
            cval, cid = cursor
            if sort == "expiring":
                # expire_at ASC NULLS LAST + id ASC. Page forward: rows with a
                # greater expire_at, or equal expire_at + greater id, or (once the
                # cursor is in the NULL tail) any NULL row with a greater id.
                if cval is None:
                    stmt = stmt.where(User.expire_at.is_(None), User.id > cid)
                else:
                    stmt = stmt.where(
                        or_(
                            User.expire_at > cval,
                            and_(User.expire_at == cval, User.id > cid),
                            User.expire_at.is_(None),
                        )
                    )
            elif desc:
                stmt = stmt.where(tuple_(col, User.id) < tuple_(cval, cid))
            else:
                stmt = stmt.where(tuple_(col, User.id) > tuple_(cval, cid))

        stmt = stmt.order_by(*self._order_by(sort)).limit(limit)
        return (await self.session.execute(stmt)).scalars().all()
