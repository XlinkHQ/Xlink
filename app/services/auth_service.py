from __future__ import annotations

import uuid
from datetime import UTC

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import hash_password_async, needs_rehash, verify_password_async
from app.core.totp import (
    generate_secret as totp_generate_secret,
)
from app.core.totp import (
    provisioning_uri as totp_provisioning_uri,
)
from app.core.totp import (
    verify as totp_verify,
)
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
            if not totp_verify(user.totp_secret, totp_code):
                raise AuthenticationError("Invalid two-factor code.", code="totp_invalid")

        if needs_rehash(user.hashed_password):
            new_hash = await hash_password_async(password)
            await self._users.update_password_hash(user, new_hash, invalidate_tokens=False)

        tokens = await self._tokens.issue_pair(user)
        return AuthResponse(user=UserRead.model_validate(user), tokens=tokens)

    async def begin_totp_enrollment(self, user_id: uuid.UUID) -> tuple[str, str]:
        secret = totp_generate_secret()
        user = await self._users.update_totp_secret(user_id, secret)
        return secret, totp_provisioning_uri(secret, user.username)

    async def confirm_totp(self, user_id: uuid.UUID, code: str) -> None:
        user = await self._users.get(user_id)
        if not user.totp_secret:
            raise AuthenticationError("Start enrollment first.", code="totp_not_started")
        if not totp_verify(user.totp_secret, code):
            raise AuthenticationError("Invalid two-factor code.", code="totp_invalid")
        await self._users.enable_totp(user_id)

    async def disable_totp(self, user_id: uuid.UUID, code: str) -> None:
        user = await self._users.get(user_id)
        if user.totp_secret and not totp_verify(user.totp_secret, code):
            raise AuthenticationError("Invalid two-factor code.", code="totp_invalid")
        await self._users.disable_totp(user_id)

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
        # Also invalidate already-issued (stateless) access tokens: bump the
        # per-user cutoff so get_authenticated_user rejects any access token
        # minted before now.
        await self._users.mark_sessions_revoked(user_id)

    async def get_authenticated_user(
        self, user_id: uuid.UUID, *, token_issued_at: int | None = None
    ) -> User:
        user = await self._users.get(user_id)
        if not user.is_active:
            raise PermissionDeniedError("Account is disabled.", code="account_disabled")

        if token_issued_at is not None:
            # fudge=1s absorbs clock granularity for password change; logout-all
            # is a deliberate revocation, so use fudge=0 (reject a token issued in
            # the same second) — the safe direction for a revocation control.
            for ts, msg, code, fudge in (
                (user.password_changed_at, "Token invalidated by a password change.", "password_changed", 1),
                (user.sessions_revoked_at, "Session was logged out.", "session_revoked", 0),
            ):
                if ts is None:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                if token_issued_at < int(ts.timestamp()) - fudge:
                    raise AuthenticationError(msg, code=code)
        return user


_DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHRzb21lc2FsdA$RdescudvJCsgt3ub+b+dWRWJTmaaJObG"
)
