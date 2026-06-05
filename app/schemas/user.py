from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field

from app.domain.user import UserRole
from app.schemas.base import APIModel, InputModel

USERNAME_PATTERN = r"^[a-zA-Z0-9_]{3,64}$"
PASSWORD_MIN_LEN = 12
PASSWORD_MAX_LEN = 128


class UserCreate(InputModel):
    email: EmailStr
    username: str = Field(pattern=USERNAME_PATTERN)
    password: str = Field(min_length=PASSWORD_MIN_LEN, max_length=PASSWORD_MAX_LEN)
    full_name: str | None = Field(default=None, max_length=255)


class UserUpdate(InputModel):
    full_name: str | None = Field(default=None, max_length=255)


class UserRead(APIModel):
    id: uuid.UUID
    email: EmailStr
    username: str
    full_name: str | None
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
