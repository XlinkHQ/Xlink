from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.user import User, UserRole

LOGIN = "/api/v1/auth/login"
USERS = "/api/v1/users"
ADMIN_PASSWORD = "admin-strong-password-1234-AB!"


async def _seed_users(app_state: AppState, count: int) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    async with app_state.db.session() as session:
        session.add(
            User(
                email="admin@example.com",
                username="admin",
                hashed_password=hash_password(ADMIN_PASSWORD),
                role=UserRole.ADMIN,
                is_sudo=True,
                created_at=base,
            )
        )
        for i in range(count):
            session.add(
                User(
                    email=f"u{i}@example.com",
                    username=f"user{i}",
                    hashed_password="x",
                    role=UserRole.USER,
                    created_at=base + timedelta(minutes=i + 1),
                )
            )


async def _admin_token(client: AsyncClient) -> str:
    resp = await client.post(LOGIN, json={"identifier": "admin", "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, resp.text
    return resp.json()["tokens"]["access_token"]


@pytest.fixture
async def admin_headers(app_state: AppState, client: AsyncClient) -> dict[str, str]:
    await _seed_users(app_state, count=5)
    token = await _admin_token(client)
    return {"Authorization": f"Bearer {token}"}


async def test_default_listing_is_keyset(client: AsyncClient, admin_headers: dict) -> None:
    resp = await client.get(USERS, headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "next_cursor" in body
    assert "meta" not in body
    assert "size" in body


async def test_keyset_pagination_walks_all_users(client: AsyncClient, admin_headers: dict) -> None:
    seen: list[str] = []
    cursor = None
    for _ in range(10):
        params = {"size": 2}
        if cursor:
            params["cursor"] = cursor
        resp = await client.get(USERS, headers=admin_headers, params=params)
        assert resp.status_code == 200
        body = resp.json()
        seen.extend(u["username"] for u in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert "admin" in seen
    assert len([u for u in seen if u.startswith("user")]) == 5
    assert len(seen) == len(set(seen))


async def test_keyset_sort_by_name_walks_ordered(client: AsyncClient, admin_headers: dict) -> None:
    seen: list[str] = []
    cursor = None
    for _ in range(10):
        params: dict = {"size": 2, "sort": "name"}
        if cursor:
            params["cursor"] = cursor
        resp = await client.get(USERS, headers=admin_headers, params=params)
        assert resp.status_code == 200
        body = resp.json()
        seen.extend(u["username"] for u in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 6
    assert len(seen) == len(set(seen))
    assert seen == sorted(seen)


async def test_explicit_page_returns_offset_shape(client: AsyncClient, admin_headers: dict) -> None:
    resp = await client.get(USERS, headers=admin_headers, params={"page": 1, "size": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert "meta" in body
    assert body["meta"]["total"] == 6
    assert body["meta"]["page"] == 1
    assert len(body["items"]) == 3


async def test_invalid_cursor_rejected(client: AsyncClient, admin_headers: dict) -> None:
    resp = await client.get(USERS, headers=admin_headers, params={"cursor": "!!!not-valid"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_cursor"


async def test_role_filter_in_keyset(client: AsyncClient, admin_headers: dict) -> None:
    resp = await client.get(USERS, headers=admin_headers, params={"role": "admin"})
    assert resp.status_code == 200
    body = resp.json()
    assert all(u["role"] == "admin" for u in body["items"])
    assert len(body["items"]) == 1
