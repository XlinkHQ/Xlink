from __future__ import annotations

from pydantic import Field

from app.schemas.base import APIModel, InputModel
from app.schemas.user import UserRead


class LoginRequest(InputModel):
    identifier: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(InputModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(InputModel):
    refresh_token: str = Field(min_length=1)


class TokenPair(APIModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthResponse(APIModel):
    user: UserRead
    tokens: TokenPair
