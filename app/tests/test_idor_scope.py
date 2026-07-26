from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.user import User, UserRole

LOGIN = "/api/v1/auth/login"
USERS = "/api/v1/users"
SUDO_PASSWORD = "sudo-admin-password-1234-AB!"


async def _seed_sudo(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        session.add(
            User(
                username="root",
                hashed_password=hash_password(SUDO_PASSWORD),
                role=UserRole.ADMIN,
                is_sudo=True,
            )
        )


async def _token(client: AsyncClient, username: str, password: str) -> str:
    resp = await client.post(LOGIN, json={"identifier": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["tokens"]["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _reseller(client: AsyncClient, sudo: dict, name: str) -> dict[str, str]:
    resp = await client.post(
        f"{USERS}/admins",
        headers=sudo,
        json={"username": name, "password": f"{name}-password-1234-AB!", "is_sudo": False},
    )
    assert resp.status_code == 201, resp.text
    return _h(await _token(client, name, f"{name}-password-1234-AB!"))


async def _make_user(client: AsyncClient, owner: dict, name: str) -> str:
    resp = await client.post(USERS, headers=owner, json={"username": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture
async def sudo_headers(app_state: AppState, client: AsyncClient) -> dict[str, str]:
    await _seed_sudo(app_state)
    return _h(await _token(client, "root", SUDO_PASSWORD))


async def test_reseller_blocked_from_other_tenant_traffic(
    client: AsyncClient, sudo_headers: dict
) -> None:
    r1 = await _reseller(client, sudo_headers, "tenant1")
    r2 = await _reseller(client, sudo_headers, "tenant2")
    victim = await _make_user(client, r1, "victim")

    for path in (
        f"/api/v1/traffic/users/{victim}/nodes",
        f"/api/v1/traffic/users/{victim}/usage-series",
    ):
        resp = await client.get(path, headers=r2)
        assert resp.status_code == 403, f"{path} -> {resp.status_code} (IDOR open)"

    resp = await client.post(f"/api/v1/traffic/users/{victim}/reset", headers=r2)
    assert resp.status_code == 403

    own = await client.get(f"/api/v1/traffic/users/{victim}/nodes", headers=r1)
    assert own.status_code == 200


async def test_reseller_blocked_from_other_tenant_sub_token(
    client: AsyncClient, sudo_headers: dict
) -> None:
    r1 = await _reseller(client, sudo_headers, "tenant1")
    r2 = await _reseller(client, sudo_headers, "tenant2")
    victim = await _make_user(client, r1, "victim")

    blocked = await client.get(f"/api/v1/subscriptions/users/{victim}/token", headers=r2)
    assert blocked.status_code == 403

    allowed = await client.get(f"/api/v1/subscriptions/users/{victim}/token", headers=r1)
    assert allowed.status_code == 200


async def test_non_sudo_cannot_pull_profile_feed(client: AsyncClient, sudo_headers: dict) -> None:
    r1 = await _reseller(client, sudo_headers, "tenant1")
    import uuid as _uuid

    resp = await client.get(f"/api/v1/subscriptions/profiles/{_uuid.uuid4()}/feed", headers=r1)
    assert resp.status_code == 403
