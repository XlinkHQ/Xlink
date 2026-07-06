from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.providers.base.exceptions import ProviderError
from app.providers.base.models import ProviderKind
from app.providers.xray.provider import XrayProvider

LOGIN = "/api/v1/auth/login"
ASSIGN = "/api/v1/assignments"
PW = "admin-strong-password-1234-AB!"


@dataclass
class Ctx:
    headers: dict[str, str]
    user_id: uuid.UUID
    node_id: uuid.UUID
    other_node_id: uuid.UUID
    profile_id: uuid.UUID
    other_profile_id: uuid.UUID


async def _seed(app_state: AppState) -> dict:
    ids: dict = {}
    async with app_state.db.session() as session:
        admin = User(
            email="admin@example.com",
            username="admin",
            hashed_password=hash_password(PW),
            role=UserRole.ADMIN,
            is_sudo=True,
        )
        session.add(admin)
        await session.flush()
        member = User(
            email="member@example.com",
            username="member",
            hashed_password=hash_password(PW),
            role=UserRole.USER,
        )
        session.add(member)
        await session.flush()
        ids["user_id"] = member.id
        node_a = Node(
            name="na",
            slug="na",
            host="10.0.0.1",
            port=443,
            max_users=100,
            node_metadata={},
            status=NodeStatus.ACTIVE,
        )
        session.add(node_a)
        await session.flush()
        ids["node_id"] = node_a.id
        node_b = Node(
            name="nb",
            slug="nb",
            host="10.0.0.2",
            port=443,
            max_users=100,
            node_metadata={},
            status=NodeStatus.ACTIVE,
        )
        session.add(node_b)
        await session.flush()
        ids["other_node_id"] = node_b.id
        prof = Profile(
            name="pa",
            slug="pa",
            provider_kind=ProviderKind.XRAY,
            node_id=node_a.id,
            protocol="vless",
            settings={},
            is_active=True,
        )
        session.add(prof)
        await session.flush()
        ids["profile_id"] = prof.id
        prof_sb = Profile(
            name="psb",
            slug="psb",
            provider_kind=ProviderKind.SING_BOX,
            node_id=node_a.id,
            protocol="vless",
            settings={},
            is_active=True,
        )
        session.add(prof_sb)
        await session.flush()
        ids["other_profile_id"] = prof_sb.id
    return ids


@pytest.fixture
async def ctx(app_state: AppState, client: AsyncClient) -> Ctx:
    ids = await _seed(app_state)
    resp = await client.post(LOGIN, json={"identifier": "admin", "password": PW})
    assert resp.status_code == 200, resp.text
    token = resp.json()["tokens"]["access_token"]
    return Ctx(headers={"Authorization": f"Bearer {token}"}, **ids)


def _payload(ctx: Ctx, **overrides) -> dict:
    base = {
        "user_id": str(ctx.user_id),
        "profile_id": str(ctx.profile_id),
        "node_id": str(ctx.node_id),
        "provider_kind": "xray",
    }
    base.update(overrides)
    return base


async def _create(client: AsyncClient, ctx: Ctx, **overrides):
    return await client.post(ASSIGN, json=_payload(ctx, **overrides), headers=ctx.headers)


async def test_create_assignment(client: AsyncClient, ctx: Ctx) -> None:
    resp = await _create(client, ctx)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user_id"] == str(ctx.user_id)
    assert body["status"] == "active"
    assert body["provider_client_id"] is not None
    assert body["version"] == 1


async def test_create_auto_selects_node_when_omitted(client: AsyncClient, ctx: Ctx) -> None:

    payload = _payload(ctx)
    payload.pop("node_id")
    resp = await client.post(ASSIGN, json=payload, headers=ctx.headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["node_id"] == str(ctx.node_id)


async def test_create_requires_admin(client: AsyncClient, ctx: Ctx) -> None:
    resp = await client.post(ASSIGN, json=_payload(ctx))
    assert resp.status_code == 401


async def test_duplicate_assignment(client: AsyncClient, ctx: Ctx) -> None:
    assert (await _create(client, ctx)).status_code == 201
    dup = await _create(client, ctx)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "assignment_exists"


async def test_invalid_user(client: AsyncClient, ctx: Ctx) -> None:
    resp = await _create(client, ctx, user_id="99999999-9999-9999-9999-999999999999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "user_not_found"


async def test_invalid_profile(client: AsyncClient, ctx: Ctx) -> None:
    resp = await _create(client, ctx, profile_id="99999999-9999-9999-9999-999999999999")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_profile"


async def test_invalid_node(client: AsyncClient, ctx: Ctx) -> None:
    resp = await _create(client, ctx, node_id="99999999-9999-9999-9999-999999999999")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_node"


async def test_profile_node_mismatch(client: AsyncClient, ctx: Ctx) -> None:
    resp = await _create(client, ctx, node_id=str(ctx.other_node_id))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "profile_node_mismatch"


async def test_profile_provider_mismatch(client: AsyncClient, ctx: Ctx) -> None:
    resp = await _create(client, ctx, provider_kind="sing-box")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "profile_provider_mismatch"


async def test_provider_failure_rollback(
    app_state: AppState, client: AsyncClient, ctx: Ctx
) -> None:
    class FailingXray(XrayProvider):
        async def create_client(self, spec):
            raise ProviderError("boom", code="provider_create_failed")

    app_state.providers.register(FailingXray(), replace=True)
    resp = await _create(client, ctx)
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "provider_create_failed"
    from sqlalchemy import func, select

    async with app_state.db.session() as session:
        count = await session.scalar(select(func.count()).select_from(ClientAssignment))
    assert count == 0


async def test_disable_assignment(client: AsyncClient, ctx: Ctx) -> None:
    a = (await _create(client, ctx)).json()
    resp = await client.post(f"{ASSIGN}/{a['id']}/disable", headers=ctx.headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "disabled"


async def test_delete_assignment(client: AsyncClient, ctx: Ctx) -> None:
    a = (await _create(client, ctx)).json()
    resp = await client.delete(f"{ASSIGN}/{a['id']}", headers=ctx.headers)
    assert resp.status_code == 204
    after = await client.get(f"{ASSIGN}/{a['id']}", headers=ctx.headers)
    assert after.status_code == 404


async def test_optimistic_conflict(client: AsyncClient, ctx: Ctx) -> None:
    a = (await _create(client, ctx)).json()
    ok = await client.patch(
        f"{ASSIGN}/{a['id']}",
        json={"status": "disabled", "expected_version": 1},
        headers=ctx.headers,
    )
    assert ok.status_code == 200
    stale = await client.patch(
        f"{ASSIGN}/{a['id']}",
        json={"status": "active", "expected_version": 1},
        headers=ctx.headers,
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"


async def _seed_assignments(app_state: AppState, ctx: Ctx) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    async with app_state.db.session() as session:
        member2 = User(
            email="m2@example.com", username="member2", hashed_password="x", role=UserRole.USER
        )
        session.add(member2)
        await session.flush()
        rows = [
            (ctx.user_id, ctx.profile_id, ctx.node_id, ProviderKind.XRAY),
            (member2.id, ctx.profile_id, ctx.node_id, ProviderKind.XRAY),
            (ctx.user_id, ctx.other_profile_id, ctx.node_id, ProviderKind.SING_BOX),
        ]
        for i, (uid, pid, nid, kind) in enumerate(rows):
            session.add(
                ClientAssignment(
                    user_id=uid,
                    profile_id=pid,
                    node_id=nid,
                    provider_kind=kind,
                    status=AssignmentStatus.ACTIVE,
                    created_at=base + timedelta(minutes=i),
                )
            )
            await session.flush()


async def test_list_assignments(app_state: AppState, client: AsyncClient, ctx: Ctx) -> None:
    await _seed_assignments(app_state, ctx)
    seen: list[str] = []
    cursor = None
    for _ in range(10):
        params = {"size": 2}
        if cursor:
            params["cursor"] = cursor
        resp = await client.get(ASSIGN, headers=ctx.headers, params=params)
        assert resp.status_code == 200
        body = resp.json()
        seen.extend(a["id"] for a in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 3
    assert len(seen) == len(set(seen))


async def test_list_by_user(app_state: AppState, client: AsyncClient, ctx: Ctx) -> None:
    await _seed_assignments(app_state, ctx)
    resp = await client.get(ASSIGN, headers=ctx.headers, params={"user_id": str(ctx.user_id)})
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


async def test_list_by_profile(app_state: AppState, client: AsyncClient, ctx: Ctx) -> None:
    await _seed_assignments(app_state, ctx)
    resp = await client.get(ASSIGN, headers=ctx.headers, params={"profile_id": str(ctx.profile_id)})
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


async def test_list_by_node(app_state: AppState, client: AsyncClient, ctx: Ctx) -> None:
    await _seed_assignments(app_state, ctx)
    resp = await client.get(ASSIGN, headers=ctx.headers, params={"node_id": str(ctx.node_id)})
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 3
