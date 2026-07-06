from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.core.lifespan import AppState
from app.repositories.user import UserRepository

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
CHANGE_PW = "/api/v1/auth/change-password"
ME = "/api/v1/users/me"

USER = {
    "email": "bob@example.com",
    "username": "bob",
    "password": "Super-Secret-Passphrase-12!",
    "full_name": "Bob",
}


async def _register(client: AsyncClient) -> dict:
    resp = await client.post(REGISTER, json=USER)
    assert resp.status_code == 201
    return resp.json()


async def _set_password_changed_at(app_state: AppState, username: str, when: datetime) -> None:
    async with app_state.db.session() as session:
        user = await UserRepository(session).get_by_username(username)
        user.password_changed_at = when
        await session.commit()


async def test_password_change_invalidates_old_access_token(
    client: AsyncClient, app_state: AppState
) -> None:
    access = (await _register(client))["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {access}"}

    assert (await client.get(ME, headers=headers)).status_code == 200

    await _set_password_changed_at(app_state, "bob", datetime.now(UTC) + timedelta(seconds=5))
    resp = await client.get(ME, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "password_changed"


async def test_token_issued_after_change_still_valid(
    client: AsyncClient, app_state: AppState
) -> None:
    access = (await _register(client))["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {access}"}

    await _set_password_changed_at(app_state, "bob", datetime.now(UTC) - timedelta(hours=1))
    assert (await client.get(ME, headers=headers)).status_code == 200


async def test_change_password_endpoint_revokes_refresh(
    client: AsyncClient,
) -> None:
    body = await _register(client)
    access = body["tokens"]["access_token"]
    refresh = body["tokens"]["refresh_token"]
    resp = await client.post(
        CHANGE_PW,
        headers={"Authorization": f"Bearer {access}"},
        json={"current_password": USER["password"], "new_password": "Another-Strong-Pass-11!"},
    )
    assert resp.status_code == 204

    after = await client.post(REFRESH, json={"refresh_token": refresh})
    assert after.status_code == 401


async def test_disabled_user_token_rejected_per_request(
    client: AsyncClient, app_state: AppState
) -> None:
    access = (await _register(client))["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {access}"}
    assert (await client.get(ME, headers=headers)).status_code == 200

    async with app_state.db.session() as session:
        user = await UserRepository(session).get_by_username("bob")
        user.is_active = False
        await session.commit()
    resp = await client.get(ME, headers=headers)
    assert resp.status_code in (401, 403)
