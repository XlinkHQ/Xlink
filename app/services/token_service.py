from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.domain.refresh_token import RefreshToken
from app.domain.user import User
from app.repositories.refresh_token import RefreshTokenRepository
from app.schemas.auth import TokenPair


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TokenService:
    def __init__(self, repo: RefreshTokenRepository, settings: Settings) -> None:
        self._repo = repo
        self._settings = settings

    async def issue_pair(self, user: User) -> TokenPair:
        subject = str(user.id)
        access, _, _ = create_access_token(
            subject, self._settings, extra_claims={"role": user.role.value}
        )
        refresh, jti, expires_at = create_refresh_token(subject, self._settings)

        await self._repo.add(
            RefreshToken(
                user_id=user.id,
                jti=jti,
                token_hash=_hash_token(refresh),
                expires_at=expires_at,
            )
        )
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=self._settings.access_token_expire_minutes * 60,
        )

    async def rotate(self, refresh_token: str, user: User) -> TokenPair:
        record = await self._consume(refresh_token)
        if record.user_id != user.id:
            await self._repo.revoke_all_for_user(record.user_id)
            raise AuthenticationError("Token does not belong to user.", code="token_invalid")
        return await self.issue_pair(user)

    async def revoke(self, refresh_token: str) -> None:
        try:
            payload = decode_token(refresh_token, self._settings, TokenType.REFRESH)
        except AuthenticationError:
            return
        await self._repo.revoke_by_jti(payload["jti"])

    async def revoke_all(self, user_id: uuid.UUID) -> None:
        await self._repo.revoke_all_for_user(user_id)

    def subject_id(self, refresh_token: str) -> uuid.UUID:
        payload = decode_token(refresh_token, self._settings, TokenType.REFRESH)
        try:
            return uuid.UUID(payload["sub"])
        except (KeyError, ValueError) as exc:
            raise AuthenticationError("Malformed token subject.", code="token_invalid") from exc

    async def _consume(self, refresh_token: str) -> RefreshToken:
        payload = decode_token(refresh_token, self._settings, TokenType.REFRESH)
        jti = payload["jti"]
        token_hash = _hash_token(refresh_token)

        record = await self._repo.consume_active(jti)

        if record is None:
            existing = await self._repo.get_by_jti(jti)
            if existing is not None and existing.token_hash == token_hash:
                await self._repo.revoke_all_for_user(existing.user_id)
                raise AuthenticationError("Refresh token reuse detected.", code="token_reuse")
            raise AuthenticationError("Unknown refresh token.", code="token_invalid")

        if record.token_hash != token_hash:
            await self._repo.revoke_all_for_user(record.user_id)
            raise AuthenticationError("Refresh token mismatch.", code="token_invalid")

        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise AuthenticationError("Refresh token expired.", code="token_expired")

        return record
