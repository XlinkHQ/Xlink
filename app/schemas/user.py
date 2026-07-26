from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator, model_validator

from app.core.security import validate_password_strength
from app.domain.user import DataResetStrategy, UserExpireStrategy, UserRole
from app.schemas.base import APIModel, InputModel


def _check_password(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    return validate_password_strength(value)


USERNAME_PATTERN = r"^[a-zA-Z0-9_]{3,64}$"
PASSWORD_MIN_LEN = 12
PASSWORD_MAX_LEN = 128


class UserCreate(InputModel):
    email: EmailStr | None = Field(default=None)
    username: str = Field(pattern=USERNAME_PATTERN)
    password: str | None = Field(
        default=None, min_length=PASSWORD_MIN_LEN, max_length=PASSWORD_MAX_LEN
    )
    full_name: str | None = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def _strong_password(cls, v: str | None) -> str | None:
        return _check_password(v)

    data_limit_bytes: int | None = Field(default=None, ge=0)
    expire_at: datetime | None = Field(default=None)
    data_reset_strategy: DataResetStrategy = Field(default=DataResetStrategy.NO_RESET)
    on_hold: bool = Field(default=False)
    on_hold_duration_seconds: int | None = Field(default=None, ge=0)
    expire_strategy: UserExpireStrategy | None = Field(default=None)
    activation_deadline: datetime | None = Field(default=None)
    device_limit: int | None = Field(default=None, ge=0)

    is_active: bool | None = Field(default=None)
    is_sudo: bool | None = Field(default=None)
    all_groups_access: bool | None = Field(default=None)
    modify_users_access: bool | None = Field(default=None)
    subscription_url_prefix: str | None = Field(default=None, max_length=512)
    admin_user_limit: int | None = Field(default=None, ge=0)
    admin_traffic_limit_bytes: int | None = Field(default=None, ge=0)
    profile_ids: list[uuid.UUID] | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_on_hold(self) -> UserCreate:
        on_hold = self.on_hold or self.expire_strategy == UserExpireStrategy.START_ON_FIRST_USE
        if on_hold:
            if self.expire_at is not None:
                raise ValueError("An on-hold user cannot also have a fixed expire_at.")
        return self


class AdminUpdate(InputModel):
    password: str | None = Field(
        default=None, min_length=PASSWORD_MIN_LEN, max_length=PASSWORD_MAX_LEN
    )
    email: EmailStr | None = Field(default=None)

    @field_validator("password")
    @classmethod
    def _strong_password(cls, v: str | None) -> str | None:
        return _check_password(v)

    is_active: bool | None = Field(default=None)
    is_sudo: bool | None = Field(default=None)
    all_groups_access: bool | None = Field(default=None)
    modify_users_access: bool | None = Field(default=None)
    subscription_url_prefix: str | None = Field(default=None, max_length=512)
    admin_user_limit: int | None = Field(default=None, ge=0)
    admin_traffic_limit_bytes: int | None = Field(default=None, ge=0)


class UserUpdate(InputModel):
    full_name: str | None = Field(default=None, max_length=255)
    data_limit_bytes: int | None = Field(default=None, ge=0)
    expire_at: datetime | None = Field(default=None)
    data_reset_strategy: DataResetStrategy | None = Field(default=None)
    on_hold: bool | None = Field(default=None)
    on_hold_duration_seconds: int | None = Field(default=None, ge=0)
    expire_strategy: UserExpireStrategy | None = Field(default=None)
    activation_deadline: datetime | None = Field(default=None)
    device_limit: int | None = Field(default=None, ge=0)
    pinned_node_ids: list[uuid.UUID] | None = Field(default=None)


class UserRead(APIModel):
    id: uuid.UUID
    email: str | None
    username: str
    full_name: str | None
    role: UserRole
    is_active: bool
    is_verified: bool
    data_limit_bytes: int | None
    expire_at: datetime | None
    data_reset_strategy: DataResetStrategy
    on_hold: bool
    expire_strategy: UserExpireStrategy
    activation_deadline: datetime | None
    device_limit: int | None
    pinned_node_ids: list[uuid.UUID] = Field(default_factory=list)
    removed: bool
    is_sudo: bool
    all_groups_access: bool
    modify_users_access: bool
    totp_enabled: bool = False
    users_data_usage: int
    owner_id: uuid.UUID | None
    subscription_url_prefix: str | None
    admin_user_limit: int | None = None
    admin_traffic_limit_bytes: int | None = None
    sub_updated_at: datetime | None
    sub_last_user_agent: str | None
    created_at: datetime
    updated_at: datetime
