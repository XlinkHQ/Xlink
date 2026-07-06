from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import lru_cache
from typing import Any

import anyio
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError


def hash_token(token: str) -> str:
    """SHA-256 hex digest of an opaque token (API keys, agent tokens, etc.)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


@lru_cache(maxsize=1)
def _hasher() -> PasswordHasher:
    s = get_settings()
    return PasswordHasher(
        time_cost=s.argon2_time_cost,
        memory_cost=s.argon2_memory_cost,
        parallelism=s.argon2_parallelism,
    )


def validate_password_strength(password: str) -> str:
    digits = sum(c.isdigit() for c in password)
    uppers = sum(c.isupper() for c in password)
    lowers = sum(c.islower() for c in password)
    specials = sum(not c.isalnum() for c in password)
    failures = []
    if digits < 2:
        failures.append("at least 2 digits")
    if uppers < 2:
        failures.append("at least 2 uppercase letters")
    if lowers < 2:
        failures.append("at least 2 lowercase letters")
    if specials < 1:
        failures.append("at least 1 special character")
    if failures:
        raise ValueError("Password must contain " + ", ".join(failures) + ".")
    return password


def hash_password(password: str) -> str:
    return _hasher().hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher().verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher().check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


async def hash_password_async(password: str) -> str:
    return await anyio.to_thread.run_sync(hash_password, password, limiter=_hash_limiter())


async def verify_password_async(password: str, password_hash: str) -> bool:
    return await anyio.to_thread.run_sync(
        verify_password, password, password_hash, limiter=_hash_limiter()
    )


@lru_cache(maxsize=1)
def _hash_limiter() -> anyio.CapacityLimiter:
    return anyio.CapacityLimiter(get_settings().password_hash_max_workers)


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    settings: Settings,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str, datetime]:
    now = datetime.now(UTC)
    expires_at = now + expires_delta
    jti = uuid.uuid4().hex
    payload: dict[str, Any] = {}
    if extra_claims:
        payload.update(extra_claims)

    payload.update(
        {
            "sub": subject,
            "type": token_type.value,
            "jti": jti,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
    )
    encoded = jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return encoded, jti, expires_at


def create_access_token(
    subject: str,
    settings: Settings,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str, datetime]:
    return _create_token(
        subject,
        TokenType.ACCESS,
        timedelta(minutes=settings.access_token_expire_minutes),
        settings,
        extra_claims,
    )


def create_refresh_token(
    subject: str,
    settings: Settings,
) -> tuple[str, str, datetime]:
    return _create_token(
        subject,
        TokenType.REFRESH,
        timedelta(days=settings.refresh_token_expire_days),
        settings,
    )


def decode_token(
    token: str,
    settings: Settings,
    expected_type: TokenType | None = None,
) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "type", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired.", code="token_expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid token.", code="token_invalid") from exc

    if expected_type is not None and payload.get("type") != expected_type.value:
        raise AuthenticationError("Invalid token type.", code="token_invalid")
    return payload
