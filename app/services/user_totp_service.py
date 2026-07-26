from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.domain.user import User
from app.services.user_service_base import UserServiceBase


class UserTotpService(UserServiceBase):
    async def update_password_hash(
        self, user: User, hashed_password: str, *, invalidate_tokens: bool = True
    ) -> User:
        user.hashed_password = hashed_password

        if invalidate_tokens:
            user.password_changed_at = datetime.now(UTC)
        await self._repo.add(user)
        if invalidate_tokens:
            from app.core.config import get_settings
            from app.repositories.refresh_token import RefreshTokenRepository
            from app.services.token_service import TokenService

            tokens = TokenService(RefreshTokenRepository(self._repo.session), get_settings())
            await tokens.revoke_all(user.id)
        await self._invalidate(user.id)
        return user

    async def mark_sessions_revoked(self, user_id: uuid.UUID) -> None:
        user = await self.get(user_id)
        user.sessions_revoked_at = datetime.now(UTC)
        await self._repo.add(user)
        await self._invalidate(user_id)

    async def update_totp_secret(self, user_id: uuid.UUID, secret: str) -> User:
        user = await self.get(user_id)
        user.totp_secret = secret
        user.totp_enabled = False
        await self._repo.add(user)
        await self._invalidate(user_id)
        return user

    async def enable_totp(self, user_id: uuid.UUID) -> User:
        user = await self.get(user_id)
        user.totp_enabled = True
        await self._repo.add(user)
        await self._invalidate(user_id)
        return user

    async def disable_totp(self, user_id: uuid.UUID) -> User:
        user = await self.get(user_id)
        user.totp_secret = None
        user.totp_enabled = False
        await self._repo.add(user)
        await self._invalidate(user_id)
        return user
