from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        jwt_secret_key="unit-test-secret-key-with-enough-length-32b!",
        env="testing",
    )


def test_password_hash_roundtrip() -> None:
    h = hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong", h)


def test_verify_password_handles_garbage_hash() -> None:
    assert verify_password("x", "not-a-valid-hash") is False


def test_access_token_roundtrip(settings: Settings) -> None:
    token, jti, _ = create_access_token("user-123", settings, extra_claims={"role": "user"})
    payload = decode_token(token, settings, TokenType.ACCESS)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"
    assert payload["jti"] == jti
    assert payload["role"] == "user"


def test_wrong_token_type_rejected(settings: Settings) -> None:
    refresh, _, _ = create_refresh_token("user-1", settings)
    with pytest.raises(AuthenticationError):
        decode_token(refresh, settings, TokenType.ACCESS)


def test_tampered_token_rejected(settings: Settings) -> None:
    token, _, _ = create_access_token("user-1", settings)
    with pytest.raises(AuthenticationError):
        decode_token(token + "x", settings, TokenType.ACCESS)


def test_jwt_secret_must_be_at_least_32_characters() -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(jwt_secret_key="too-short", env="testing")


def test_jwt_secret_rejects_default_values() -> None:
    with pytest.raises(ValidationError, match="too weak"):
        Settings(jwt_secret_key="replace_me_with_openssl_rand_hex_32", env="testing")


def test_jwt_secret_rejects_low_variety_values() -> None:
    with pytest.raises(ValidationError, match="too weak"):
        Settings(jwt_secret_key="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", env="testing")


def test_jwt_algorithm_is_restricted_to_hs256() -> None:
    with pytest.raises(ValidationError):
        Settings(
            jwt_secret_key="strong-secret-for-algorithm-test-123!",
            jwt_algorithm="RS256",
            env="testing",
        )


def test_production_rejects_default_database_password() -> None:
    with pytest.raises(ValidationError, match="default password"):
        Settings(
            env="production",
            trusted_hosts=["api.example.com"],
            jwt_secret_key="production-secret-key-with-strong-variety-123!",
            postgres_password="change_me_in_production",
        )
