from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.providers.base.models import ProviderKind

LOGIN = "/api/v1/auth/login"
PROFILES = "/api/v1/profiles"
ADMIN_PASSWORD = "admin-strong-password-1234-AB!"


@dataclass
class Ctx:
    headers: dict[str, str]
    node_id: uuid.UUID
    other_node_id: uuid.UUID


async def _seed(app_state: AppState) -> tuple[uuid.UUID, uuid.UUID]:
    async with app_state.db.session() as session:
        session.add(
            User(
                email="admin@example.com",
                username="admin",
                hashed_password=hash_password(ADMIN_PASSWORD),
                role=UserRole.ADMIN,
                is_sudo=True,
            )
        )
        await session.flush()

        node_a = Node(
            name="node-a",
            slug="node-a",
            host="10.0.0.1",
            port=443,
            max_users=100,
            node_metadata={},
            status=NodeStatus.ACTIVE,
        )
        session.add(node_a)
        await session.flush()

        node_b = Node(
            name="node-b",
            slug="node-b",
            host="10.0.0.2",
            port=443,
            max_users=100,
            node_metadata={},
            status=NodeStatus.ACTIVE,
        )
        session.add(node_b)
        await session.flush()
        return node_a.id, node_b.id


@pytest.fixture
async def ctx(app_state: AppState, client: AsyncClient) -> Ctx:
    node_id, other_node_id = await _seed(app_state)
    resp = await client.post(LOGIN, json={"identifier": "admin", "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, resp.text
    token = resp.json()["tokens"]["access_token"]
    return Ctx(
        headers={"Authorization": f"Bearer {token}"},
        node_id=node_id,
        other_node_id=other_node_id,
    )


def _payload(ctx: Ctx, **overrides) -> dict:
    base = {
        "name": "Profile 1",
        "slug": "prof-1",
        "provider_kind": "xray",
        "node_id": str(ctx.node_id),
        "protocol": "vless",
        "settings": {"flow": "vision"},
    }
    base.update(overrides)
    return base


async def _create(client: AsyncClient, ctx: Ctx, **overrides):
    return await client.post(PROFILES, json=_payload(ctx, **overrides), headers=ctx.headers)


async def test_create_profile(client: AsyncClient, ctx: Ctx) -> None:
    resp = await _create(client, ctx)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"] == "prof-1"
    assert body["provider_kind"] == "xray"
    assert body["node_id"] == str(ctx.node_id)
    assert body["is_active"] is True
    assert body["version"] == 1
    assert body["settings"] == {"flow": "vision"}


async def test_create_requires_admin(client: AsyncClient, ctx: Ctx) -> None:
    resp = await client.post(PROFILES, json=_payload(ctx))
    assert resp.status_code == 401


async def test_duplicate_slug(client: AsyncClient, ctx: Ctx) -> None:
    assert (await _create(client, ctx)).status_code == 201
    dup = await _create(client, ctx, name="Other")
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "slug_taken"


async def test_invalid_node(client: AsyncClient, ctx: Ctx) -> None:
    resp = await _create(client, ctx, node_id="99999999-9999-9999-9999-999999999999")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_node"


async def test_registered_providers_accepted(client: AsyncClient, ctx: Ctx) -> None:
    from app.providers.wireguard.provider import _generate_keypair

    wg_priv, wg_pub = _generate_keypair()
    cases = {
        "xray": ("vless", {"flow": "vision"}),
        # WireGuard requires an interface address and the SERVER keypair
        # (privateKey drives the node interface, publicKey becomes the client
        # subscription's peer key), and the pair must actually match.
        "wireguard": (
            "wireguard",
            {"address": "10.8.0.2/32", "privateKey": wg_priv, "publicKey": wg_pub},
        ),
        "sing-box": ("trojan", {}),
        "hysteria": ("hysteria2", {}),
    }
    for kind, (protocol, settings) in cases.items():
        resp = await _create(
            client,
            ctx,
            provider_kind=kind,
            protocol=protocol,
            slug=f"prof-{kind}",
            name=f"Profile {kind}",
            settings=settings,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["provider_kind"] == kind


async def test_protocol_provider_mismatch_rejected(client: AsyncClient, ctx: Ctx) -> None:
    resp = await _create(client, ctx, provider_kind="hysteria", protocol="vless", slug="bad")
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "protocol_provider_mismatch"


async def test_update_profile(client: AsyncClient, ctx: Ctx) -> None:
    prof = (await _create(client, ctx)).json()
    resp = await client.patch(
        f"{PROFILES}/{prof['id']}",
        json={"name": "Renamed", "protocol": "trojan"},
        headers=ctx.headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Renamed"
    assert body["protocol"] == "trojan"
    assert body["version"] == 2


async def test_optimistic_conflict(client: AsyncClient, ctx: Ctx) -> None:
    prof = (await _create(client, ctx)).json()
    ok = await client.patch(
        f"{PROFILES}/{prof['id']}",
        json={"name": "v2", "expected_version": 1},
        headers=ctx.headers,
    )
    assert ok.status_code == 200
    stale = await client.patch(
        f"{PROFILES}/{prof['id']}",
        json={"name": "v3", "expected_version": 1},
        headers=ctx.headers,
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"


async def test_disable_profile(client: AsyncClient, ctx: Ctx) -> None:
    prof = (await _create(client, ctx)).json()
    resp = await client.post(f"{PROFILES}/{prof['id']}/disable", headers=ctx.headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False


async def _seed_profiles(app_state: AppState, ctx: Ctx) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    specs = [
        ("xray-a", ProviderKind.XRAY, ctx.node_id),
        ("xray-b", ProviderKind.XRAY, ctx.other_node_id),
        ("singbox-a", ProviderKind.SING_BOX, ctx.node_id),
    ]
    async with app_state.db.session() as session:
        for i, (slug, kind, node_id) in enumerate(specs):
            session.add(
                Profile(
                    name=slug,
                    slug=slug,
                    provider_kind=kind,
                    node_id=node_id,
                    protocol="vless",
                    settings={},
                    is_active=True,
                    created_at=base + timedelta(minutes=i),
                )
            )
            await session.flush()


async def test_list_profiles(app_state: AppState, client: AsyncClient, ctx: Ctx) -> None:
    await _seed_profiles(app_state, ctx)
    seen: list[str] = []
    cursor = None
    for _ in range(10):
        params = {"size": 2}
        if cursor:
            params["cursor"] = cursor
        resp = await client.get(PROFILES, headers=ctx.headers, params=params)
        assert resp.status_code == 200
        body = resp.json()
        assert "next_cursor" in body
        assert "meta" not in body
        seen.extend(p["slug"] for p in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 3
    assert len(seen) == len(set(seen))


async def test_list_by_node(app_state: AppState, client: AsyncClient, ctx: Ctx) -> None:
    await _seed_profiles(app_state, ctx)
    resp = await client.get(PROFILES, headers=ctx.headers, params={"node_id": str(ctx.node_id)})
    assert resp.status_code == 200
    body = resp.json()
    assert {p["slug"] for p in body["items"]} == {"xray-a", "singbox-a"}


async def test_list_by_provider(app_state: AppState, client: AsyncClient, ctx: Ctx) -> None:
    await _seed_profiles(app_state, ctx)
    resp = await client.get(PROFILES, headers=ctx.headers, params={"provider_kind": "xray"})
    assert resp.status_code == 200
    body = resp.json()
    assert {p["slug"] for p in body["items"]} == {"xray-a", "xray-b"}


async def test_get_profile_not_found(client: AsyncClient, ctx: Ctx) -> None:
    resp = await client.get(f"{PROFILES}/00000000-0000-0000-0000-000000000000", headers=ctx.headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "profile_not_found"
