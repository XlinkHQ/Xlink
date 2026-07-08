"""Typed models mirroring the XLink API schemas.

These are intentionally light dataclasses (no runtime validation) built from the
JSON the panel returns. Field names and types match the panel's Pydantic
`*Read` models exactly. Unknown/extra keys are ignored so the SDK keeps working
if the panel adds fields.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field, fields
from typing import Any, Optional, TypeVar
from uuid import UUID

T = TypeVar("T", bound="_Model")


def _parse_uuid(value: Any) -> Optional[UUID]:
    if value is None or isinstance(value, UUID):
        return value
    return UUID(str(value))


def _parse_dt(value: Any) -> Optional[_dt.datetime]:
    if value is None or isinstance(value, _dt.datetime):
        return value
    # Pydantic emits ISO-8601; accept a trailing "Z".
    return _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class _Model:
    """Mixin: build a dataclass from a JSON dict, ignoring extra keys and
    coercing UUID / datetime string fields declared via metadata."""

    @classmethod
    def from_dict(cls: type[T], data: dict[str, Any]) -> T:
        kwargs: dict[str, Any] = {}
        for f in fields(cls):  # type: ignore[arg-type]
            if f.name not in data:
                continue
            raw = data[f.name]
            coerce = f.metadata.get("coerce")
            if coerce == "uuid":
                kwargs[f.name] = _parse_uuid(raw)
            elif coerce == "uuid_list":
                kwargs[f.name] = [_parse_uuid(v) for v in (raw or [])]
            elif coerce == "datetime":
                kwargs[f.name] = _parse_dt(raw)
            else:
                kwargs[f.name] = raw
        return cls(**kwargs)  # type: ignore[call-arg]


def _uuid_field(**kw: Any):
    return field(metadata={"coerce": "uuid"}, **kw)


def _uuid_list_field(**kw: Any):
    return field(metadata={"coerce": "uuid_list"}, **kw)


def _dt_field(**kw: Any):
    return field(metadata={"coerce": "datetime"}, **kw)


@dataclass
class User(_Model):
    """Mirrors `UserRead`."""

    id: UUID = _uuid_field()
    username: str = ""
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str = "user"
    is_active: bool = True
    is_verified: bool = False
    data_limit_bytes: Optional[int] = None
    expire_at: Optional[_dt.datetime] = _dt_field(default=None)
    data_reset_strategy: str = "no_reset"
    on_hold: bool = False
    expire_strategy: str = "never"
    activation_deadline: Optional[_dt.datetime] = _dt_field(default=None)
    device_limit: Optional[int] = None
    pinned_node_ids: list[UUID] = _uuid_list_field(default_factory=list)
    removed: bool = False
    is_sudo: bool = False
    all_groups_access: bool = False
    modify_users_access: bool = False
    totp_enabled: bool = False
    users_data_usage: int = 0
    owner_id: Optional[UUID] = _uuid_field(default=None)
    subscription_url_prefix: Optional[str] = None
    admin_user_limit: Optional[int] = None
    admin_traffic_limit_bytes: Optional[int] = None
    sub_updated_at: Optional[_dt.datetime] = _dt_field(default=None)
    sub_last_user_agent: Optional[str] = None
    created_at: Optional[_dt.datetime] = _dt_field(default=None)
    updated_at: Optional[_dt.datetime] = _dt_field(default=None)


@dataclass
class SubscriptionToken(_Model):
    """Response of `/subscriptions/my/token` and `/subscriptions/users/{id}/token`."""

    token: str = ""
    subscription_url: str = ""


@dataclass
class UserUsage(_Model):
    """One item of `POST /traffic/users/usage`."""

    user_id: UUID = _uuid_field()
    used_bytes: int = 0
    limit_bytes: int = 0
    unlimited: bool = False


@dataclass
class UsageSeriesPoint(_Model):
    """One item of `/traffic/users/{id}/usage-series` (daily buckets)."""

    date: str = ""
    upload_bytes: int = 0
    download_bytes: int = 0
    total_bytes: int = 0


@dataclass
class UserNodeUsage(_Model):
    """One item of `/traffic/users/{id}/nodes`."""

    node_id: UUID = _uuid_field()
    node_name: str = ""
    total_bytes: int = 0


@dataclass
class ResetUsageResult(_Model):
    """Response of `POST /traffic/users/{id}/reset`."""

    reset_assignments: int = 0


@dataclass
class Node(_Model):
    """Mirrors `NodeRead`."""

    id: UUID = _uuid_field()
    name: str = ""
    slug: str = ""
    host: str = ""
    port: int = 0
    status: str = "active"
    last_seen_at: Optional[_dt.datetime] = _dt_field(default=None)
    max_users: int = 0
    current_users: int = 0
    usage_coefficient: float = 1.0
    socks_enabled: bool = False
    socks_address: Optional[str] = None
    socks_username: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    created_at: Optional[_dt.datetime] = _dt_field(default=None)
    updated_at: Optional[_dt.datetime] = _dt_field(default=None)


@dataclass
class Profile(_Model):
    """Mirrors `ProfileRead`."""

    id: UUID = _uuid_field()
    name: str = ""
    slug: str = ""
    provider_kind: str = "xray"
    node_id: UUID = _uuid_field(default=None)  # type: ignore[assignment]
    protocol: str = ""
    settings: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    version: int = 1
    created_at: Optional[_dt.datetime] = _dt_field(default=None)
    updated_at: Optional[_dt.datetime] = _dt_field(default=None)


@dataclass
class Group(_Model):
    """Mirrors `GroupRead`."""

    id: UUID = _uuid_field()
    name: str = ""
    slug: str = ""
    profile_ids: list[UUID] = _uuid_list_field(default_factory=list)
    version: int = 1
    created_at: Optional[_dt.datetime] = _dt_field(default=None)
    updated_at: Optional[_dt.datetime] = _dt_field(default=None)


@dataclass
class Assignment(_Model):
    """Mirrors `AssignmentRead`."""

    id: UUID = _uuid_field()
    user_id: UUID = _uuid_field(default=None)  # type: ignore[assignment]
    profile_id: UUID = _uuid_field(default=None)  # type: ignore[assignment]
    node_id: UUID = _uuid_field(default=None)  # type: ignore[assignment]
    provider_kind: str = "xray"
    provider_client_id: Optional[str] = None
    status: str = "active"
    expires_at: Optional[_dt.datetime] = _dt_field(default=None)
    traffic_limit_bytes: Optional[int] = None
    used_bytes: int = 0
    version: int = 1
    created_at: Optional[_dt.datetime] = _dt_field(default=None)
    updated_at: Optional[_dt.datetime] = _dt_field(default=None)


@dataclass
class CursorPage(_Model):
    """Cursor-paginated envelope: `{items, next_cursor, size}`.

    `items` are left as raw dicts; the client method maps them into the right
    model. Use `next_cursor` as the `cursor=` argument to fetch the next page.
    """

    items: list[Any] = field(default_factory=list)
    next_cursor: Optional[str] = None
    size: int = 0
