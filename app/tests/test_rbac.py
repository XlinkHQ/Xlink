"""RBAC end to end over HTTP: roles narrow or widen what a non-sudo admin may do,
limits bound what they may grant, and role-less admins keep legacy behaviour."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.user import User, UserRole

API = "/api/v1"
SUDO_PW = "sudo-admin-password-1234-AB!"
RESELLER_PW = "reseller-password-1234-AB!"
USER_PW = "plain-user-password-1234-AB!"
GB = 1024**3


async def _token(c: AsyncClient, username: str, password: str) -> dict[str, str]:
    r = await c.post(f"{API}/auth/login", json={"identifier": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}


@pytest.fixture
async def ctx(app_state: AppState, client: AsyncClient):
    async with app_state.db.session() as s:
        s.add(
            User(
                username="root",
                hashed_password=hash_password(SUDO_PW),
                role=UserRole.ADMIN,
                is_sudo=True,
            )
        )
    sudo = await _token(client, "root", SUDO_PW)
    r = await client.post(
        f"{API}/users/admins",
        headers=sudo,
        json={"username": "reseller", "password": RESELLER_PW, "is_sudo": False},
    )
    assert r.status_code == 201, r.text
    reseller_id = r.json()["id"]
    # a user the reseller does NOT own
    r = await client.post(
        f"{API}/users", headers=sudo, json={"username": "foreign", "password": USER_PW}
    )
    assert r.status_code == 201, r.text
    return client, sudo, reseller_id, r.json()["id"]


async def _role(c, sudo, permissions, limits=None) -> str:
    r = await c.post(
        f"{API}/admin-roles",
        headers=sudo,
        json={
            "name": f"role-{len(str(permissions))}-{id(permissions)}",
            "permissions": permissions,
            "limits": limits or {},
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _assign(c, sudo, admin_id, role_id) -> None:
    r = await c.patch(
        f"{API}/users/admins/{admin_id}", headers=sudo, json={"admin_role_id": role_id}
    )
    assert r.status_code == 200, r.text


async def test_read_all_lets_a_reseller_see_users_it_does_not_own(ctx) -> None:
    c, sudo, rid, foreign = ctx
    await _assign(c, sudo, rid, await _role(c, sudo, {"users": {"read": 2}}))
    h = await _token(c, "reseller", RESELLER_PW)
    r = await c.get(f"{API}/users/{foreign}", headers=h)
    assert r.status_code == 200, r.text


async def test_read_own_hides_foreign_users(ctx) -> None:
    c, sudo, rid, foreign = ctx
    await _assign(c, sudo, rid, await _role(c, sudo, {"users": {"read": 1}}))
    h = await _token(c, "reseller", RESELLER_PW)
    r = await c.get(f"{API}/users/{foreign}", headers=h)
    assert r.status_code in (403, 404)


async def test_missing_action_is_denied(ctx) -> None:
    c, sudo, rid, _ = ctx
    await _assign(c, sudo, rid, await _role(c, sudo, {"users": {"read": 1, "create": 1}}))
    h = await _token(c, "reseller", RESELLER_PW)
    r = await c.post(
        f"{API}/users",
        headers=h,
        json={"username": "mine", "password": USER_PW, "data_limit_bytes": GB},
    )
    mine = r.json()["id"]
    r = await c.delete(f"{API}/users/{mine}", headers=h)
    assert r.status_code == 403
    assert r.json().get("code") == "role_forbidden" or "role" in r.text


async def test_action_scope_is_per_action(ctx) -> None:
    """delete: OWN must not borrow a broader update: ALL."""
    c, sudo, rid, foreign = ctx
    await _assign(
        c, sudo, rid, await _role(c, sudo, {"users": {"read": 2, "update": 2, "delete": 1}})
    )
    h = await _token(c, "reseller", RESELLER_PW)
    r = await c.patch(f"{API}/users/{foreign}", headers=h, json={"full_name": "x"})
    assert r.status_code == 200, r.text
    r = await c.delete(f"{API}/users/{foreign}", headers=h)
    assert r.status_code == 403


async def test_limits_are_enforced(ctx) -> None:
    c, sudo, rid, _ = ctx
    await _assign(
        c,
        sudo,
        rid,
        await _role(
            c,
            sudo,
            {"users": {"create": 1, "read": 1}},
            {"max_users": 1, "data_limit_max": 10 * GB, "expire_max_days": 30},
        ),
    )
    h = await _token(c, "reseller", RESELLER_PW)

    r = await c.post(f"{API}/users", headers=h, json={"username": "user0", "password": USER_PW})
    assert r.status_code in (400, 422), "unlimited user must be refused under a data ceiling"

    r = await c.post(
        f"{API}/users",
        headers=h,
        json={
            "username": "user1",
            "password": USER_PW,
            "data_limit_bytes": 50 * GB,
            "expire_at": "2099-01-01T00:00:00Z",
        },
    )
    assert r.status_code in (400, 422)

    from datetime import UTC, datetime, timedelta

    soon = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    r = await c.post(
        f"{API}/users",
        headers=h,
        json={
            "username": "user2",
            "password": USER_PW,
            "data_limit_bytes": 5 * GB,
            "expire_at": soon,
        },
    )
    assert r.status_code == 201, r.text

    r = await c.post(
        f"{API}/users",
        headers=h,
        json={
            "username": "user3",
            "password": USER_PW,
            "data_limit_bytes": 5 * GB,
            "expire_at": soon,
        },
    )
    assert r.status_code in (400, 422), "max_users=1 must stop the second user"


async def test_invalid_role_is_rejected(ctx) -> None:
    c, sudo, *_ = ctx
    r = await c.post(
        f"{API}/admin-roles",
        headers=sudo,
        json={"name": "bad", "permissions": {"users": {"delte": 2}}},
    )
    assert r.status_code in (400, 422)


async def test_role_in_use_cannot_be_deleted(ctx) -> None:
    c, sudo, rid, _ = ctx
    role = await _role(c, sudo, {"users": {"read": 1}})
    await _assign(c, sudo, rid, role)
    r = await c.delete(f"{API}/admin-roles/{role}", headers=sudo)
    assert r.status_code == 409


async def test_clearing_the_role_restores_legacy_rules(ctx) -> None:
    c, sudo, rid, foreign = ctx
    await _assign(c, sudo, rid, await _role(c, sudo, {"users": {"read": 2}}))
    await _assign(c, sudo, rid, None)
    h = await _token(c, "reseller", RESELLER_PW)
    r = await c.get(f"{API}/users/{foreign}", headers=h)
    assert r.status_code in (403, 404), "legacy rules: a reseller only sees its own users"


async def test_roles_api_is_sudo_only(ctx) -> None:
    c, sudo, rid, _ = ctx
    h = await _token(c, "reseller", RESELLER_PW)
    assert (await c.get(f"{API}/admin-roles", headers=h)).status_code == 403
    assert (await c.post(f"{API}/admin-roles", headers=h, json={"name": "x"})).status_code == 403


async def test_explicit_null_cannot_lift_a_user_past_role_ceilings(ctx) -> None:
    from datetime import UTC, datetime, timedelta

    c, sudo, rid, _ = ctx
    await _assign(
        c,
        sudo,
        rid,
        await _role(
            c,
            sudo,
            {"users": {"create": 1, "read": 1, "update": 1, "bulk": 1}},
            {"data_limit_max": 10 * GB, "expire_max_days": 30},
        ),
    )
    h = await _token(c, "reseller", RESELLER_PW)
    soon = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    r = await c.post(
        f"{API}/users",
        headers=h,
        json={"username": "capped", "password": USER_PW, "data_limit_bytes": GB, "expire_at": soon},
    )
    assert r.status_code == 201, r.text
    uid = r.json()["id"]

    for body in ({"data_limit_bytes": None}, {"expire_at": None}):
        r = await c.patch(f"{API}/users/{uid}", headers=h, json=body)
        assert r.status_code in (400, 422), (body, r.text)

    r = await c.post(
        f"{API}/users/bulk",
        headers=h,
        json={"action": "set_data_limit", "user_ids": [uid], "data_limit_bytes": None},
    )
    assert r.status_code in (400, 422), r.text
    r = await c.post(
        f"{API}/users/bulk",
        headers=h,
        json={"action": "extend_expiry", "user_ids": [uid], "extend_days": 365},
    )
    assert r.status_code in (400, 422), r.text
