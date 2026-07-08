"""Synchronous client for the XLink panel HTTP API.

Authenticates with an API key (``xlk_<prefix>_<secret>``) sent in the
``X-API-Key`` header. An API key is bound to an admin account, so the client
operates with that admin's scope (read + write on users it owns; read on
nodes/profiles/groups/assignments).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Union
from uuid import UUID

import httpx

from .errors import XLinkAPIError
from .models import (
    Assignment,
    CursorPage,
    Group,
    Node,
    Profile,
    ResetUsageResult,
    SubscriptionToken,
    UsageSeriesPoint,
    User,
    UserNodeUsage,
    UserUsage,
)

_UUIDLike = Union[str, UUID]


def _uuid(value: _UUIDLike) -> str:
    return str(value)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _drop_none(data: dict[str, Any]) -> dict[str, Any]:
    """Strip unset (None) keys so we send only fields the caller provided.

    The panel's input models use ``extra="forbid"``, but a ``None`` for an
    optional field is valid — we drop them purely to keep PATCH bodies minimal
    and avoid clobbering values with nulls the caller never intended.
    """

    return {k: v for k, v in data.items() if v is not None}


class XLinkClient:
    """A minimal, typed client for the XLink panel API.

    Example::

        client = XLinkClient("https://panel.example.com", "xlk_ab12_secret...")
        user = client.create_user(username="alice", data_limit_bytes=10 * 2**30)
        sub = client.get_user_subscription_token(user.id)
        print(sub.subscription_url)
        client.close()

    Also usable as a context manager (``with XLinkClient(...) as client:``).
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 30.0,
        api_prefix: str = "/api/v1",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_prefix = api_prefix.rstrip("/")
        self._http = httpx.Client(
            base_url=f"{self.base_url}{self.api_prefix}",
            headers={
                "X-API-Key": api_key,
                "Accept": "application/json",
            },
            timeout=timeout,
        )

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "XLinkClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- low-level ---------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        resp = self._http.request(method, path, **kwargs)
        if resp.status_code >= 400:
            try:
                body: Any = resp.json()
            except ValueError:
                body = {"error": {"message": resp.text or resp.reason_phrase}}
            raise XLinkAPIError.from_response(resp.status_code, body)
        return resp

    def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = self._request(method, path, **kwargs)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # =====================================================================
    # Users  —  /users
    # =====================================================================

    def create_user(
        self,
        *,
        username: str,
        email: Optional[str] = None,
        password: Optional[str] = None,
        full_name: Optional[str] = None,
        data_limit_bytes: Optional[int] = None,
        expire_at: Optional[datetime] = None,
        data_reset_strategy: Optional[str] = None,
        on_hold: Optional[bool] = None,
        on_hold_duration_seconds: Optional[int] = None,
        expire_strategy: Optional[str] = None,
        activation_deadline: Optional[datetime] = None,
        device_limit: Optional[int] = None,
        profile_ids: Optional[list[_UUIDLike]] = None,
    ) -> User:
        """`POST /users` — create an end user (201).

        Pass ``profile_ids`` to also assign the user to those profiles in one
        call (user + working config without a second request).
        """

        body = _drop_none(
            {
                "username": username,
                "email": email,
                "password": password,
                "full_name": full_name,
                "data_limit_bytes": data_limit_bytes,
                "expire_at": _iso(expire_at),
                "data_reset_strategy": data_reset_strategy,
                "on_hold": on_hold,
                "on_hold_duration_seconds": on_hold_duration_seconds,
                "expire_strategy": expire_strategy,
                "activation_deadline": _iso(activation_deadline),
                "device_limit": device_limit,
                "profile_ids": [_uuid(p) for p in profile_ids] if profile_ids else None,
            }
        )
        return User.from_dict(self._json("POST", "/users", json=body))

    def get_user(self, user_id: _UUIDLike) -> User:
        """`GET /users/{user_id}`."""

        return User.from_dict(self._json("GET", f"/users/{_uuid(user_id)}"))

    def list_users(
        self,
        *,
        cursor: Optional[str] = None,
        size: int = 50,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        include_removed: bool = False,
        search: Optional[str] = None,
        sort: Optional[str] = None,
    ) -> CursorPage:
        """`GET /users` — cursor-paginated list.

        Returns a :class:`CursorPage` whose ``items`` are :class:`User`.
        Pass the previous page's ``next_cursor`` as ``cursor`` for the next page.
        """

        params = _drop_none(
            {
                "size": size,
                "cursor": cursor,
                "role": role,
                "is_active": is_active,
                "include_removed": include_removed or None,
                "search": search,
                "sort": sort,
            }
        )
        page = CursorPage.from_dict(self._json("GET", "/users", params=params))
        page.items = [User.from_dict(i) for i in page.items]
        return page

    def update_user(
        self,
        user_id: _UUIDLike,
        *,
        full_name: Optional[str] = None,
        data_limit_bytes: Optional[int] = None,
        expire_at: Optional[datetime] = None,
        data_reset_strategy: Optional[str] = None,
        on_hold: Optional[bool] = None,
        on_hold_duration_seconds: Optional[int] = None,
        expire_strategy: Optional[str] = None,
        activation_deadline: Optional[datetime] = None,
        device_limit: Optional[int] = None,
        pinned_node_ids: Optional[list[_UUIDLike]] = None,
    ) -> User:
        """`PATCH /users/{user_id}` — update quota / limits."""

        body = _drop_none(
            {
                "full_name": full_name,
                "data_limit_bytes": data_limit_bytes,
                "expire_at": _iso(expire_at),
                "data_reset_strategy": data_reset_strategy,
                "on_hold": on_hold,
                "on_hold_duration_seconds": on_hold_duration_seconds,
                "expire_strategy": expire_strategy,
                "activation_deadline": _iso(activation_deadline),
                "device_limit": device_limit,
                "pinned_node_ids": (
                    [_uuid(p) for p in pinned_node_ids] if pinned_node_ids else None
                ),
            }
        )
        return User.from_dict(self._json("PATCH", f"/users/{_uuid(user_id)}", json=body))

    def delete_user(self, user_id: _UUIDLike, *, purge: bool = False) -> None:
        """`DELETE /users/{user_id}` (204). Soft-delete by default; ``purge=True``
        removes it permanently."""

        self._request(
            "DELETE",
            f"/users/{_uuid(user_id)}",
            params={"purge": "true"} if purge else None,
        )

    def enable_user(self, user_id: _UUIDLike) -> User:
        """`POST /users/{user_id}/enable`."""

        return User.from_dict(self._json("POST", f"/users/{_uuid(user_id)}/enable"))

    def disable_user(self, user_id: _UUIDLike) -> User:
        """`POST /users/{user_id}/disable`."""

        return User.from_dict(self._json("POST", f"/users/{_uuid(user_id)}/disable"))

    def restore_user(self, user_id: _UUIDLike) -> User:
        """`POST /users/{user_id}/restore` — undo a soft-delete."""

        return User.from_dict(self._json("POST", f"/users/{_uuid(user_id)}/restore"))

    def revoke_user_subscription(self, user_id: _UUIDLike) -> User:
        """`POST /users/{user_id}/revoke-subscription` — rotate the subscription
        token, instantly invalidating every existing subscription URL."""

        return User.from_dict(
            self._json("POST", f"/users/{_uuid(user_id)}/revoke-subscription")
        )

    # =====================================================================
    # Subscription  —  /subscriptions
    # =====================================================================

    def get_user_subscription_token(self, user_id: _UUIDLike) -> SubscriptionToken:
        """`GET /subscriptions/users/{user_id}/token` — the signed subscription
        URL + token for a specific user (admin scope)."""

        data = self._json("GET", f"/subscriptions/users/{_uuid(user_id)}/token")
        return SubscriptionToken.from_dict(data)

    def get_my_subscription_token(self, scope: str = "USER") -> SubscriptionToken:
        """`GET /subscriptions/my/token` — subscription URL for the identity that
        owns the API key. ``scope`` is one of ``USER``/``PROFILE``/``ASSIGNMENT``."""

        data = self._json("GET", "/subscriptions/my/token", params={"scope": scope})
        return SubscriptionToken.from_dict(data)

    # =====================================================================
    # Usage / traffic  —  /traffic
    # =====================================================================

    def get_user_usage(self, user_id: _UUIDLike) -> UserUsage:
        """Used/limit bytes for one user, via `POST /traffic/users/usage`
        (the panel exposes usage as a batch endpoint; this is the single-user
        convenience wrapper)."""

        rows = self.get_users_usage([user_id])
        if not rows:
            return UserUsage(user_id=UUID(_uuid(user_id)))
        return rows[0]

    def get_users_usage(self, user_ids: list[_UUIDLike]) -> list[UserUsage]:
        """`POST /traffic/users/usage` — batch used/limit bytes (max 500 ids)."""

        data = self._json(
            "POST",
            "/traffic/users/usage",
            json={"user_ids": [_uuid(u) for u in user_ids]},
        )
        return [UserUsage.from_dict(row) for row in data or []]

    def get_user_usage_series(
        self, user_id: _UUIDLike, *, days: int = 14
    ) -> list[UsageSeriesPoint]:
        """`GET /traffic/users/{user_id}/usage-series` — daily upload/download
        buckets for the last ``days`` days."""

        data = self._json(
            "GET",
            f"/traffic/users/{_uuid(user_id)}/usage-series",
            params={"days": days},
        )
        return [UsageSeriesPoint.from_dict(p) for p in data or []]

    def get_user_node_usage(self, user_id: _UUIDLike) -> list[UserNodeUsage]:
        """`GET /traffic/users/{user_id}/nodes` — per-node usage for a user."""

        data = self._json("GET", f"/traffic/users/{_uuid(user_id)}/nodes")
        return [UserNodeUsage.from_dict(r) for r in data or []]

    def reset_user_usage(self, user_id: _UUIDLike) -> ResetUsageResult:
        """`POST /traffic/users/{user_id}/reset` — zero a user's usage counter."""

        data = self._json("POST", f"/traffic/users/{_uuid(user_id)}/reset")
        return ResetUsageResult.from_dict(data)

    # =====================================================================
    # Nodes  —  /nodes  (read)
    # =====================================================================

    def list_nodes(
        self, *, cursor: Optional[str] = None, size: int = 50, status: Optional[str] = None
    ) -> CursorPage:
        """`GET /nodes` — cursor-paginated list of :class:`Node`. ``status`` is
        the ``status_filter`` query param (active/disabled/offline)."""

        params = _drop_none({"size": size, "cursor": cursor, "status_filter": status})
        page = CursorPage.from_dict(self._json("GET", "/nodes", params=params))
        page.items = [Node.from_dict(i) for i in page.items]
        return page

    def get_node(self, node_id: _UUIDLike) -> Node:
        """`GET /nodes/{node_id}`."""

        return Node.from_dict(self._json("GET", f"/nodes/{_uuid(node_id)}"))

    # =====================================================================
    # Profiles  —  /profiles  (read)
    # =====================================================================

    def list_profiles(
        self,
        *,
        cursor: Optional[str] = None,
        size: int = 50,
        provider_kind: Optional[str] = None,
        node_id: Optional[_UUIDLike] = None,
        is_active: Optional[bool] = None,
    ) -> CursorPage:
        """`GET /profiles` — cursor-paginated list of :class:`Profile`."""

        params = _drop_none(
            {
                "size": size,
                "cursor": cursor,
                "provider_kind": provider_kind,
                "node_id": _uuid(node_id) if node_id is not None else None,
                "is_active": is_active,
            }
        )
        page = CursorPage.from_dict(self._json("GET", "/profiles", params=params))
        page.items = [Profile.from_dict(i) for i in page.items]
        return page

    def get_profile(self, profile_id: _UUIDLike) -> Profile:
        """`GET /profiles/{profile_id}`."""

        return Profile.from_dict(self._json("GET", f"/profiles/{_uuid(profile_id)}"))

    # =====================================================================
    # Groups  —  /groups  (read)
    # =====================================================================

    def list_groups(self) -> list[Group]:
        """`GET /groups` — all groups (not paginated)."""

        return [Group.from_dict(g) for g in self._json("GET", "/groups") or []]

    def get_group(self, group_id: _UUIDLike) -> Group:
        """`GET /groups/{group_id}`."""

        return Group.from_dict(self._json("GET", f"/groups/{_uuid(group_id)}"))

    # =====================================================================
    # Assignments  —  /assignments
    # =====================================================================

    def create_assignment(
        self,
        *,
        user_id: _UUIDLike,
        profile_id: _UUIDLike,
        provider_kind: str,
        node_id: Optional[_UUIDLike] = None,
        expires_at: Optional[datetime] = None,
        traffic_limit_bytes: Optional[int] = None,
        group_id: Optional[_UUIDLike] = None,
    ) -> Assignment:
        """`POST /assignments` — bind a user to a profile/inbound (201)."""

        body = _drop_none(
            {
                "user_id": _uuid(user_id),
                "profile_id": _uuid(profile_id),
                "provider_kind": provider_kind,
                "node_id": _uuid(node_id) if node_id is not None else None,
                "expires_at": _iso(expires_at),
                "traffic_limit_bytes": traffic_limit_bytes,
                "group_id": _uuid(group_id) if group_id is not None else None,
            }
        )
        return Assignment.from_dict(self._json("POST", "/assignments", json=body))

    def list_assignments(
        self,
        *,
        cursor: Optional[str] = None,
        size: int = 50,
        user_id: Optional[_UUIDLike] = None,
        profile_id: Optional[_UUIDLike] = None,
        node_id: Optional[_UUIDLike] = None,
        provider_kind: Optional[str] = None,
        status: Optional[str] = None,
    ) -> CursorPage:
        """`GET /assignments` — cursor-paginated list of :class:`Assignment`."""

        params = _drop_none(
            {
                "size": size,
                "cursor": cursor,
                "user_id": _uuid(user_id) if user_id is not None else None,
                "profile_id": _uuid(profile_id) if profile_id is not None else None,
                "node_id": _uuid(node_id) if node_id is not None else None,
                "provider_kind": provider_kind,
                "status_filter": status,
            }
        )
        page = CursorPage.from_dict(self._json("GET", "/assignments", params=params))
        page.items = [Assignment.from_dict(i) for i in page.items]
        return page

    def get_assignment(self, assignment_id: _UUIDLike) -> Assignment:
        """`GET /assignments/{assignment_id}`."""

        return Assignment.from_dict(
            self._json("GET", f"/assignments/{_uuid(assignment_id)}")
        )
