from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.core.cache import CacheProtocol
from app.core.exceptions import NotFoundError, ValidationError
from app.core.pagination import decode_cursor, encode_cursor
from app.core.security import hash_password_async
from app.domain.user import User, UserRole
from app.repositories.user import UserRepository
from app.schemas.pagination import CursorParams, PaginationParams
from app.schemas.user import UserCreate, UserUpdate

_USER_CACHE_PREFIX = "user:id:"


class UserService:
    def __init__(self, repo: UserRepository, cache: CacheProtocol) -> None:
        self._repo = repo
        self._cache = cache

    async def create(self, data: UserCreate) -> User:
        hashed = await hash_password_async(data.password)
        user = User(
            email=data.email.lower(),
            username=data.username,
            full_name=data.full_name,
            hashed_password=hashed,
            role=UserRole.USER,
        )
        return await self._repo.create_user(user)

    async def get(self, user_id: uuid.UUID) -> User:
        user = await self._repo.get(user_id)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")
        return user

    async def get_by_identifier(self, identifier: str) -> User | None:
        return await self._repo.get_by_identifier(identifier)

    async def update_password_hash(self, user: User, hashed_password: str) -> User:
        user.hashed_password = hashed_password
        await self._repo.add(user)
        await self._invalidate(user.id)
        return user

    async def update_profile(self, user_id: uuid.UUID, data: UserUpdate) -> User:
        user = await self.get(user_id)
        if data.full_name is not None:
            user.full_name = data.full_name
        await self._repo.add(user)
        await self._invalidate(user_id)
        return user

    async def list_users(
        self,
        params: PaginationParams,
        *,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> tuple[Sequence[User], int]:
        return await self._repo.list_paginated(
            offset=params.offset,
            limit=params.limit,
            role=role,
            is_active=is_active,
        )

    async def list_users_keyset(
        self,
        params: CursorParams,
        *,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[User], str | None]:
        cursor = None
        if params.cursor is not None:
            try:
                cursor = decode_cursor(params.cursor)
            except ValueError as exc:
                raise ValidationError(str(exc), code="invalid_cursor") from exc

        rows = list(
            await self._repo.list_keyset(
                limit=params.limit + 1,
                cursor=cursor,
                role=role,
                is_active=is_active,
            )
        )

        next_cursor = None
        if len(rows) > params.limit:
            rows = rows[: params.limit]
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)
        return rows, next_cursor

    async def _invalidate(self, user_id: uuid.UUID) -> None:
        await self._cache.delete(f"{_USER_CACHE_PREFIX}{user_id}")
