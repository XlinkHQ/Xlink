from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.node import Node, NodeStatus
from app.domain.user import User, UserRole

LOGIN = "/api/v1/auth/login"
NODES = "/api/v1/nodes"
ADMIN_PASSWORD = "admin-strong-password-1234"

NODE_PAYLOAD = {
    "name": "Frankfurt 1",
    "slug": "fra-1",
    "host": "10.0.0.5",
    "port": 443,
    "max_users": 100,
    "metadata": {"region": "eu"},
}


async def _seed_admin(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        session.add(
            User(
                email="admin@example.com",
                username="admin",
                hashed_password=hash_password(ADMIN_PASSWORD),
                role=UserRole.ADMIN,
            )
        )


@pytest.fixture
async def admin_headers(app_state: AppState, client: AsyncClient) -> dict[str, str]:
    await _seed_admin(app_state)
    resp = await client.post(LOGIN, json={"identifier": "admin", "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, resp.text
    token = resp.json()["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _create(client: AsyncClient, headers: dict, **overrides) -> dict:
    payload = {**NODE_PAYLOAD, **overrides}
    return await client.post(NODES, json=payload, headers=headers)


async def _seed_nodes(app_state: AppState, count: int, *, status=NodeStatus.OFFLINE) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    async with app_state.db.session() as session:
        for i in range(count):
            session.add(
                Node(
                    name=f"node-{i}",
                    slug=f"node-{i}",
                    host=f"10.9.0.{i}",
                    port=443,
                    max_users=10,
                    node_metadata={},
                    status=status,
                    created_at=base + timedelta(minutes=i),
                )
            )


async def test_create_node(client: AsyncClient, admin_headers: dict) -> None:
    resp = await _create(client, admin_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"] == "fra-1"
    assert body["status"] == "offline"
    assert body["metadata"] == {"region": "eu"}
    assert body["version"] == 1
    assert body["current_users"] == 0
    assert body["id"]


async def test_create_requires_admin(client: AsyncClient) -> None:
    resp = await client.post(NODES, json=NODE_PAYLOAD)
    assert resp.status_code == 401


async def test_duplicate_slug_conflicts(client: AsyncClient, admin_headers: dict) -> None:
    first = await _create(client, admin_headers)
    assert first.status_code == 201
    second = await _create(client, admin_headers, host="10.0.0.6")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "slug_taken"


async def test_update_node(client: AsyncClient, admin_headers: dict) -> None:
    node = (await _create(client, admin_headers)).json()
    resp = await client.patch(
        f"{NODES}/{node['id']}",
        json={"name": "Frankfurt Prime", "max_users": 250},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Frankfurt Prime"
    assert body["max_users"] == 250
    assert body["version"] == 2


async def test_optimistic_update_conflict(client: AsyncClient, admin_headers: dict) -> None:
    node = (await _create(client, admin_headers)).json()
    ok = await client.patch(
        f"{NODES}/{node['id']}",
        json={"name": "v2", "expected_version": 1},
        headers=admin_headers,
    )
    assert ok.status_code == 200
    stale = await client.patch(
        f"{NODES}/{node['id']}",
        json={"name": "v3", "expected_version": 1},
        headers=admin_headers,
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"


async def test_disable_node(client: AsyncClient, admin_headers: dict) -> None:
    node = (await _create(client, admin_headers)).json()
    resp = await client.post(f"{NODES}/{node['id']}/disable", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "disabled"


async def test_heartbeat_update(client: AsyncClient, admin_headers: dict) -> None:
    node = (await _create(client, admin_headers)).json()
    assert node["status"] == "offline"
    assert node["last_seen_at"] is None

    resp = await client.post(
        f"{NODES}/{node['id']}/heartbeat",
        json={"current_users": 42},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current_users"] == 42
    assert body["status"] == "active"
    assert body["last_seen_at"] is not None


async def test_heartbeat_respects_explicit_status(client: AsyncClient, admin_headers: dict) -> None:
    node = (await _create(client, admin_headers)).json()
    await client.post(f"{NODES}/{node['id']}/disable", headers=admin_headers)
    resp = await client.post(
        f"{NODES}/{node['id']}/heartbeat",
        json={"current_users": 5, "status": "disabled"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"


async def test_list_nodes_keyset(
    app_state: AppState, client: AsyncClient, admin_headers: dict
) -> None:
    await _seed_nodes(app_state, count=5)

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        params = {"size": 2}
        if cursor:
            params["cursor"] = cursor
        resp = await client.get(NODES, headers=admin_headers, params=params)
        assert resp.status_code == 200
        body = resp.json()
        assert "next_cursor" in body
        assert "meta" not in body
        seen.extend(n["slug"] for n in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert len(seen) == 5
    assert len(seen) == len(set(seen))


async def test_list_nodes_status_filter(
    app_state: AppState, client: AsyncClient, admin_headers: dict
) -> None:
    await _seed_nodes(app_state, count=2, status=NodeStatus.OFFLINE)
    await _seed_active(app_state)

    resp = await client.get(NODES, headers=admin_headers, params={"status_filter": "active"})
    assert resp.status_code == 200
    body = resp.json()
    assert all(n["status"] == "active" for n in body["items"])
    assert any(n["slug"] == "active-1" for n in body["items"])


async def _seed_active(app_state: AppState) -> None:
    async with app_state.db.session() as session:
        session.add(
            Node(
                name="active",
                slug="active-1",
                host="10.9.9.9",
                port=443,
                max_users=10,
                node_metadata={},
                status=NodeStatus.ACTIVE,
                created_at=datetime(2026, 2, 1, tzinfo=UTC),
            )
        )


async def test_get_node_not_found(client: AsyncClient, admin_headers: dict) -> None:
    resp = await client.get(f"{NODES}/00000000-0000-0000-0000-000000000000", headers=admin_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "node_not_found"


async def test_invalid_slug_rejected(client: AsyncClient, admin_headers: dict) -> None:
    resp = await _create(client, admin_headers, slug="Invalid Slug!")
    assert resp.status_code == 422
