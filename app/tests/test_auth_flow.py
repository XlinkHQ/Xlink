from __future__ import annotations

from httpx import AsyncClient

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/users/me"

VALID_USER = {
    "email": "alice@example.com",
    "username": "alice",
    "password": "super-secret-passphrase",
    "full_name": "Alice",
}


async def _register(client: AsyncClient, **overrides: object) -> dict:
    payload = {**VALID_USER, **overrides}
    resp = await client.post(REGISTER, json=payload)
    return resp


async def test_register_returns_tokens_and_user(client: AsyncClient) -> None:
    resp = await _register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["role"] == "user"
    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]
    assert "password" not in body["user"]


async def test_duplicate_email_conflicts(client: AsyncClient) -> None:
    await _register(client)
    resp = await _register(client, username="alice2")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "email_taken"


async def test_login_and_access_me(client: AsyncClient) -> None:
    await _register(client)
    resp = await client.post(
        LOGIN, json={"identifier": "alice", "password": VALID_USER["password"]}
    )
    assert resp.status_code == 200
    access = resp.json()["tokens"]["access_token"]

    me = await client.get(ME, headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


async def test_login_wrong_password_rejected(client: AsyncClient) -> None:
    await _register(client)
    resp = await client.post(LOGIN, json={"identifier": "alice", "password": "nope-nope-nope"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


async def test_me_requires_auth(client: AsyncClient) -> None:
    resp = await client.get(ME)
    assert resp.status_code == 401


async def test_refresh_rotates_and_reuse_detected(client: AsyncClient) -> None:
    reg = (await _register(client)).json()
    old_refresh = reg["tokens"]["refresh_token"]

    rotated = await client.post(REFRESH, json={"refresh_token": old_refresh})
    assert rotated.status_code == 200
    new_refresh = rotated.json()["refresh_token"]
    assert new_refresh != old_refresh

    reused = await client.post(REFRESH, json={"refresh_token": old_refresh})
    assert reused.status_code == 401


async def test_logout_revokes_refresh(client: AsyncClient) -> None:
    reg = (await _register(client)).json()
    refresh = reg["tokens"]["refresh_token"]

    logout = await client.post(LOGOUT, json={"refresh_token": refresh})
    assert logout.status_code == 204

    after = await client.post(REFRESH, json={"refresh_token": refresh})
    assert after.status_code == 401


async def test_non_admin_cannot_list_users(client: AsyncClient) -> None:
    reg = (await _register(client)).json()
    access = reg["tokens"]["access_token"]
    resp = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {access}"})
    assert resp.status_code == 403
