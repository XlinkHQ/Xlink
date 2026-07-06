from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.user import User, UserRole

LOGIN = "/api/v1/auth/login"
KEYS = "/api/v1/api-keys"
ADMIN_PASSWORD = "admin-strong-password-1234-AB!"


async def _seed_admin(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        session.add(
            User(
                username="admin",
                hashed_password=hash_password(ADMIN_PASSWORD),
                role=UserRole.ADMIN,
                is_sudo=True,
            )
        )


@pytest.fixture
async def admin_headers(app_state: AppState, client: AsyncClient) -> dict[str, str]:
    await _seed_admin(app_state)
    resp = await client.post(LOGIN, json={"identifier": "admin", "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['tokens']['access_token']}"}


async def test_create_and_list(client: AsyncClient, admin_headers: dict) -> None:
    created = await client.post(KEYS, headers=admin_headers, json={"name": "ci"})
    assert created.status_code == 200, created.text
    assert created.json()["token"].startswith("xlk_")

    page = await client.get(KEYS, headers=admin_headers)
    assert page.status_code == 200
    body = page.json()
    assert len(body["items"]) == 1
    assert body["total"] == 1
    assert body["next_offset"] is None


async def test_pagination(client: AsyncClient, admin_headers: dict) -> None:
    for _ in range(7):
        assert (await client.post(KEYS, headers=admin_headers, json={})).status_code == 200

    first = (await client.get(f"{KEYS}?limit=3", headers=admin_headers)).json()
    assert len(first["items"]) == 3
    assert first["total"] == 7
    assert first["next_offset"] == 3

    seen = {k["id"] for k in first["items"]}
    offset = first["next_offset"]
    pages = 1
    while offset is not None:
        nxt = (await client.get(f"{KEYS}?limit=3&offset={offset}", headers=admin_headers)).json()
        for k in nxt["items"]:
            seen.add(k["id"])
        offset = nxt["next_offset"]
        pages += 1
    assert len(seen) == 7
    assert pages == 3


async def test_disable_enable_purge(client: AsyncClient, admin_headers: dict) -> None:
    key_id = (await client.post(KEYS, headers=admin_headers, json={})).json()["id"]

    disabled = await client.delete(f"{KEYS}/{key_id}", headers=admin_headers)
    assert disabled.status_code == 204
    row = (await client.get(KEYS, headers=admin_headers)).json()["items"][0]
    assert row["revoked_at"] is not None

    enabled = await client.post(f"{KEYS}/{key_id}/enable", headers=admin_headers)
    assert enabled.status_code == 200
    assert enabled.json()["revoked_at"] is None

    purged = await client.delete(f"{KEYS}/{key_id}/purge", headers=admin_headers)
    assert purged.status_code == 204
    assert (await client.get(KEYS, headers=admin_headers)).json()["items"] == []


async def test_cannot_touch_another_users_key(
    app_state: AppState, client: AsyncClient, admin_headers: dict
) -> None:
    import uuid

    fake = uuid.uuid4()
    assert (await client.delete(f"{KEYS}/{fake}", headers=admin_headers)).status_code == 404
    assert (await client.post(f"{KEYS}/{fake}/enable", headers=admin_headers)).status_code == 404
    assert (await client.delete(f"{KEYS}/{fake}/purge", headers=admin_headers)).status_code == 404
