from __future__ import annotations

import contextlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.security import (
    hash_token as _hash_token,
)
from app.domain.refresh_token import RefreshToken
from app.domain.user import User
from app.repositories.refresh_token import RefreshTokenRepository
from app.schemas.auth import TokenPair

_REUSE_GRACE_SECONDS = 10


class TokenService:
    def __init__(self, repo: RefreshTokenRepository, settings: Settings, cache=None) -> None:
        self._repo = repo
        self._settings = settings
        self._cache = cache

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

    def _grace_key(self, jti: str) -> str:
        return f"refresh-grace:{jti}"

    async def rotate(self, refresh_token: str, user: User) -> TokenPair:
        payload = decode_token(refresh_token, self._settings, TokenType.REFRESH)
        jti = payload.get("jti", "")
        if self._cache is not None and jti:
            with contextlib.suppress(Exception):
                cached = await self._cache.get_json(self._grace_key(jti))
                if cached:
                    return TokenPair(**cached)
        record = await self._consume(refresh_token)
        if record.user_id != user.id:
            await self._repo.revoke_all_for_user(record.user_id)
            raise AuthenticationError("Token does not belong to user.", code="token_invalid")
        pair = await self.issue_pair(user)
        if self._cache is not None and jti:
            with contextlib.suppress(Exception):
                await self._cache.set_json(
                    self._grace_key(jti),
                    {
                        "access_token": pair.access_token,
                        "refresh_token": pair.refresh_token,
                        "expires_in": pair.expires_in,
                    },
                    ttl=_REUSE_GRACE_SECONDS,
                )
        return pair

    async def revoke(self, refresh_token: str) -> None:
        try:
            payload = decode_token(refresh_token, self._settings, TokenType.REFRESH)
        except AuthenticationError:
            return
        jti = payload["jti"]
        await self._repo.revoke_by_jti(jti)
        # rotate() answers from the grace cache BEFORE it reads the database, so
        # the revoked flags above are invisible while the cached successor
        # survives. Drop it or logout does not actually log the session out.
        await self._drop_grace(jti)

    async def revoke_all(self, user_id: uuid.UUID) -> None:
        jtis = await self._repo.recent_jtis_for_user(user_id)
        await self._repo.revoke_all_for_user(user_id)
        for jti in jtis:
            await self._drop_grace(jti)

    async def _drop_grace(self, jti: str) -> None:
        if self._cache is None or not jti:
            return
        with contextlib.suppress(Exception):
            await self._cache.delete(self._grace_key(jti))

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
            if existing is not None and hmac.compare_digest(existing.token_hash, token_hash):
                revoked_at = existing.updated_at
                if revoked_at is not None and revoked_at.tzinfo is None:
                    revoked_at = revoked_at.replace(tzinfo=UTC)
                grace_cutoff = datetime.now(UTC) - timedelta(seconds=_REUSE_GRACE_SECONDS)
                if revoked_at is not None and revoked_at >= grace_cutoff:
                    if not await self._repo.claim_grace(existing.jti):
                        await self._repo.revoke_all_for_user(existing.user_id)
                        raise AuthenticationError(
                            "Refresh token already replayed during grace period.",
                            code="token_reuse",
                        )
                    return existing
                await self._repo.revoke_all_for_user(existing.user_id)
                raise AuthenticationError("Refresh token reuse detected.", code="token_reuse")
            raise AuthenticationError("Unknown refresh token.", code="token_invalid")

        if not hmac.compare_digest(record.token_hash, token_hash):
            await self._repo.revoke_all_for_user(record.user_id)
            raise AuthenticationError("Refresh token mismatch.", code="token_invalid")

        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise AuthenticationError("Refresh token expired.", code="token_expired")

        return record
