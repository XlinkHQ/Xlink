from __future__ import annotations

import uuid

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import hash_password_async, needs_rehash, verify_password_async
from app.domain.user import User
from app.schemas.auth import AuthResponse, TokenPair
from app.schemas.user import UserCreate, UserRead
from app.services.token_service import TokenService
from app.services.user_service import UserService


class AuthService:
    def __init__(
        self,
        user_service: UserService,
        token_service: TokenService,
    ) -> None:
        self._users = user_service
        self._tokens = token_service

    async def register(self, data: UserCreate) -> AuthResponse:
        user = await self._users.create(data)
        tokens = await self._tokens.issue_pair(user)
        return AuthResponse(user=UserRead.model_validate(user), tokens=tokens)

    async def login(self, identifier: str, password: str) -> AuthResponse:
        user = await self._users.get_by_identifier(identifier)

        if user is None:
            await verify_password_async(password, _DUMMY_HASH)
            raise AuthenticationError("Invalid credentials.", code="invalid_credentials")

        if not await verify_password_async(password, user.hashed_password):
            raise AuthenticationError("Invalid credentials.", code="invalid_credentials")

        if not user.is_active:
            raise PermissionDeniedError("Account is disabled.", code="account_disabled")

        if needs_rehash(user.hashed_password):
            new_hash = await hash_password_async(password)
            await self._users.update_password_hash(user, new_hash)

        tokens = await self._tokens.issue_pair(user)
        return AuthResponse(user=UserRead.model_validate(user), tokens=tokens)

    async def refresh(self, refresh_token: str) -> TokenPair:
        user_id = self._tokens.subject_id(refresh_token)
        user = await self._users.get(user_id)
        if not user.is_active:
            raise PermissionDeniedError("Account is disabled.", code="account_disabled")
        return await self._tokens.rotate(refresh_token, user)

    async def logout(self, refresh_token: str) -> None:
        await self._tokens.revoke(refresh_token)

    async def logout_everywhere(self, user_id: uuid.UUID) -> None:
        await self._tokens.revoke_all(user_id)

    async def get_authenticated_user(self, user_id: uuid.UUID) -> User:
        user = await self._users.get(user_id)
        if not user.is_active:
            raise PermissionDeniedError("Account is disabled.", code="account_disabled")
        return user


_DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHRzb21lc2FsdA$RdescudvJCsgt3ub+b+dWRWJTmaaJObG"
)
