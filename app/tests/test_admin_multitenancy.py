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


@pytest.fixture
async def sudo_headers(app_state: AppState, client: AsyncClient) -> dict[str, str]:
    await _seed_sudo(app_state)
    return _h(await _token(client, "root", SUDO_PASSWORD))


async def _make_reseller(client: AsyncClient, sudo_headers: dict, **caps) -> dict[str, str]:
    resp = await client.post(
        f"{USERS}/admins",
        headers=sudo_headers,
        json={
            "username": "reseller",
            "password": "reseller-password-1234-AB!",
            "is_sudo": False,
            **caps,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["is_sudo"] is False
    return _h(await _token(client, "reseller", "reseller-password-1234-AB!"))


async def test_non_sudo_cannot_create_admins(client: AsyncClient, sudo_headers: dict) -> None:
    reseller = await _make_reseller(client, sudo_headers)
    resp = await client.post(
        f"{USERS}/admins",
        headers=reseller,
        json={"username": "x", "password": "another-password-1234-AB!"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "sudo_required"


async def test_reseller_owns_users_it_creates_and_scoping(
    client: AsyncClient, sudo_headers: dict
) -> None:
    reseller = await _make_reseller(client, sudo_headers)

    created = await client.post(USERS, headers=reseller, json={"username": "client_a"})
    assert created.status_code == 201, created.text

    other = await client.post(USERS, headers=sudo_headers, json={"username": "client_b"})
    assert other.status_code == 201

    listing = await client.get(USERS, headers=reseller, params={"role": "user"})
    names = {u["username"] for u in listing.json()["items"]}
    assert "client_a" in names
    assert "client_b" not in names

    sudo_listing = await client.get(USERS, headers=sudo_headers, params={"role": "user"})
    sudo_names = {u["username"] for u in sudo_listing.json()["items"]}
    assert {"client_a", "client_b"} <= sudo_names

    other_id = other.json()["id"]
    resp = await client.delete(f"{USERS}/{other_id}", headers=reseller)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "user_out_of_scope"


async def test_read_only_admin_cannot_modify(client: AsyncClient, sudo_headers: dict) -> None:
    reseller = await _make_reseller(client, sudo_headers, modify_users_access=False)
    resp = await client.post(USERS, headers=reseller, json={"username": "nope"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "read_only_admin"


async def test_subscription_url_prefix_override(
    app_state: AppState, client: AsyncClient, sudo_headers: dict
) -> None:
    prefix = "https://sub.reseller.example"
    await _make_reseller(client, sudo_headers, subscription_url_prefix=prefix)

    reseller_hdr = _h(await _token(client, "reseller", "reseller-password-1234-AB!"))
    created = await client.post(USERS, headers=reseller_hdr, json={"username": "client_c"})
    uid = created.json()["id"]

    resp = await client.get(f"/api/v1/subscriptions/users/{uid}/token", headers=sudo_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["subscription_url"].startswith(prefix)


async def test_update_admin_toggles_sudo_and_password(
    client: AsyncClient, sudo_headers: dict[str, str]
) -> None:

    await _make_reseller(client, sudo_headers)
    admin_id = (await client.get(f"{USERS}?role=admin", headers=sudo_headers)).json()["items"]
    reseller = next(a for a in admin_id if a["username"] == "reseller")
    resp = await client.patch(
        f"{USERS}/admins/{reseller['id']}",
        headers=sudo_headers,
        json={"is_sudo": True, "password": "New-Reseller-Password-99!"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_sudo"] is True

    assert (
        await client.post(
            LOGIN, json={"identifier": "reseller", "password": "New-Reseller-Password-99!"}
        )
    ).status_code == 200


async def test_update_admin_requires_sudo(
    client: AsyncClient, sudo_headers: dict[str, str]
) -> None:
    reseller_headers = await _make_reseller(client, sudo_headers, modify_users_access=True)
    rows = (await client.get(f"{USERS}?role=admin", headers=sudo_headers)).json()["items"]
    target = next(a for a in rows if a["username"] == "reseller")

    resp = await client.patch(
        f"{USERS}/admins/{target['id']}", headers=reseller_headers, json={"is_sudo": True}
    )
    assert resp.status_code == 403


async def test_enable_disable_admin_users(
    client: AsyncClient, app_state: AppState, sudo_headers: dict[str, str]
) -> None:
    reseller_headers = await _make_reseller(client, sudo_headers, modify_users_access=True)

    created = await client.post(
        USERS,
        headers=reseller_headers,
        json={"username": "owned_user", "password": "Owned-User-Password-11!"},
    )
    assert created.status_code == 201, created.text
    rows = (await client.get(f"{USERS}?role=admin", headers=sudo_headers)).json()["items"]
    reseller = next(a for a in rows if a["username"] == "reseller")

    resp = await client.post(f"{USERS}/admins/{reseller['id']}/disable-users", headers=sudo_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["affected"] == 1
    async with app_state.db.session() as session:
        from app.repositories.user import UserRepository

        u = await UserRepository(session).get_by_username("owned_user")
        assert u.is_active is False

    resp = await client.post(f"{USERS}/admins/{reseller['id']}/enable-users", headers=sudo_headers)
    assert resp.json()["affected"] == 1
