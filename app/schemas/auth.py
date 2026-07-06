from __future__ import annotations

from pydantic import Field, field_validator

from app.core.security import validate_password_strength
from app.schemas.base import APIModel, InputModel
from app.schemas.user import UserRead


class LoginRequest(InputModel):
    identifier: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)
    totp_code: str | None = Field(default=None, max_length=12)


class TotpConfirmRequest(InputModel):
    code: str = Field(min_length=6, max_length=12)


class TotpEnrollResponse(APIModel):
    secret: str
    otpauth_uri: str


class RefreshRequest(InputModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(InputModel):
    refresh_token: str = Field(min_length=1)


class ChangePasswordRequest(InputModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _strong(cls, v: str) -> str:
        return validate_password_strength(v)


class TokenPair(APIModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthResponse(APIModel):
    user: UserRead
    tokens: TokenPair
