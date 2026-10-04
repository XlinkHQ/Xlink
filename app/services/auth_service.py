from __future__ import annotations

import uuid
from datetime import UTC

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import hash_password_async, needs_rehash, verify_password_async
from app.core.totp import REPLAY_TTL_S
from app.core.totp import (
    generate_secret as totp_generate_secret,
)
from app.core.totp import matching_step as totp_matching_step
from app.core.totp import (
    provisioning_uri as totp_provisioning_uri,
)
from app.domain.user import User
from app.schemas.auth import AuthResponse, TokenPair
from app.schemas.user import UserCreate, UserRead
from app.services.token_service import TokenService
from app.services.user_service import UserService
from app.services.user_totp_service import UserTotpService


class AuthService:
    def __init__(
        self,
        user_service: UserService,
        token_service: TokenService,
        totp_service: UserTotpService,
    ) -> None:
        self._users = user_service
        self._tokens = token_service
        self._totp = totp_service

    async def _totp_ok(self, user: User, code: str) -> bool:
        """Verify a TOTP code once. A code stays valid for ~90 s (±1 step), so
        without this a phished or shoulder-surfed code could be replayed in
        that window. The used step is recorded in Redis; if Redis is down the
        check fails closed, like the auth rate limiter."""
        step = totp_matching_step(user.totp_secret or "", code)
        if step is None:
            return False
        cache = getattr(self._tokens, "_cache", None)
        if cache is None:
            return True
        try:
            fresh = await cache.client.set(
                f"totp:used:{user.id}:{step}", b"1", nx=True, ex=REPLAY_TTL_S
            )
        except Exception:
            return False
        return bool(fresh)

    async def register(self, data: UserCreate) -> AuthResponse:
        user = await self._users.create(data)
        tokens = await self._tokens.issue_pair(user)
        return AuthResponse(user=UserRead.model_validate(user), tokens=tokens)

    async def login(
        self, identifier: str, password: str, totp_code: str | None = None
    ) -> AuthResponse:
        user = await self._users.get_by_identifier(identifier)

        if user is None or user.hashed_password is None:
            await verify_password_async(password, _DUMMY_HASH)
            raise AuthenticationError("Invalid credentials.", code="invalid_credentials")

        if not await verify_password_async(password, user.hashed_password):
            raise AuthenticationError("Invalid credentials.", code="invalid_credentials")

        if not user.is_active:
            raise PermissionDeniedError("Account is disabled.", code="account_disabled")

        if user.totp_enabled and user.totp_secret:
            if not totp_code:
                raise AuthenticationError("A two-factor code is required.", code="totp_required")
            if not await self._totp_ok(user, totp_code):
                raise AuthenticationError("Invalid two-factor code.", code="totp_invalid")

        if needs_rehash(user.hashed_password):
            new_hash = await hash_password_async(password)
            await self._totp.update_password_hash(user, new_hash, invalidate_tokens=False)

        tokens = await self._tokens.issue_pair(user)
        return AuthResponse(user=UserRead.model_validate(user), tokens=tokens)

    async def begin_totp_enrollment(
        self, user_id: uuid.UUID, *, code: str | None = None
    ) -> tuple[str, str]:
        existing = await self._users.get(user_id)
        already_active = bool(existing.totp_enabled and existing.totp_secret)
        if already_active and (not code or not await self._totp_ok(existing, code)):
            raise AuthenticationError(
                "Two-factor is already enabled — provide your current code to re-enroll.",
                code="totp_reenroll_requires_code",
            )
        secret = totp_generate_secret()
        user = await self._totp.update_totp_secret(user_id, secret)
        return secret, totp_provisioning_uri(secret, user.username)

    async def confirm_totp(self, user_id: uuid.UUID, code: str) -> None:
        user = await self._users.get(user_id)
        if not user.totp_secret:
            raise AuthenticationError("Start enrollment first.", code="totp_not_started")
        if not await self._totp_ok(user, code):
            raise AuthenticationError("Invalid two-factor code.", code="totp_invalid")
        await self._totp.enable_totp(user_id)

    async def disable_totp(self, user_id: uuid.UUID, code: str) -> None:
        user = await self._users.get(user_id)
        if user.totp_secret and not await self._totp_ok(user, code):
            raise AuthenticationError("Invalid two-factor code.", code="totp_invalid")
        await self._totp.disable_totp(user_id)

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
        await self._totp.mark_sessions_revoked(user_id)

    async def get_authenticated_user(
        self, user_id: uuid.UUID, *, token_issued_at: int | None = None
    ) -> User:
        user = await self._users.get(user_id)
        if not user.is_active:
            raise PermissionDeniedError("Account is disabled.", code="account_disabled")

        if token_issued_at is not None:
            for ts, msg, code, reject_equal in (
                (
                    user.password_changed_at,
                    "Token invalidated by a password change.",
                    "password_changed",
                    False,
                ),
                (user.sessions_revoked_at, "Session was logged out.", "session_revoked", True),
            ):
                if ts is None:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                cutoff = int(ts.timestamp())
                if reject_equal:
                    if token_issued_at <= cutoff:
                        raise AuthenticationError(msg, code=code)
                elif token_issued_at < cutoff - 1:
                    raise AuthenticationError(msg, code=code)
        return user


_DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHRzb21lc2FsdA$RdescudvJCsgt3ub+b+dWRWJTmaaJObG"
)
