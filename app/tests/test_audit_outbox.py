from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.audit_log import AuditLog
from app.domain.user import User, UserRole

LOGIN = "/api/v1/auth/login"
ADMIN_PASSWORD = "admin-strong-password-1234-AB!"


async def _seed_admin(app_state: AppState) -> None:
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


async def _count_audit(app_state: AppState) -> int:
    async with app_state.db.session() as session:
        return int(await session.scalar(select(func.count()).select_from(AuditLog)) or 0)


async def _wait_for_audit(app_state: AppState, minimum: int) -> int:
    for _ in range(40):
        count = await _count_audit(app_state)
        if count >= minimum:
            return count
        await asyncio.sleep(0.05)
    return await _count_audit(app_state)


@pytest.fixture
async def admin_headers(app_state: AppState, client: AsyncClient) -> dict[str, str]:
    await _seed_admin(app_state)
    resp = await client.post(LOGIN, json={"identifier": "admin", "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['tokens']['access_token']}"}


async def test_authenticated_mutation_is_audited(
    app_state: AppState, client: AsyncClient, admin_headers: dict
) -> None:
    before = await _count_audit(app_state)
    resp = await client.post("/api/v1/auth/register", json={"username": "subscriber"})
    assert resp.status_code == 201, resp.text

    after = await _wait_for_audit(app_state, before + 1)
    assert after == before

    resp = await client.post(
        "/api/v1/users/admins",
        headers=admin_headers,
        json={"username": "reseller2", "password": "Reseller-Strong-Pw-123!"},
    )
    assert resp.status_code in (200, 201), resp.text

    after_auth = await _wait_for_audit(app_state, before + 1)
    assert after_auth >= before + 1

    async with app_state.db.session() as session:
        row = (
            await session.execute(
                select(AuditLog).order_by(AuditLog.created_at.desc()).limit(1)
            )
        ).scalar_one()
    assert row.method == "POST"
    assert row.actor_username == "admin"
    assert row.status_code in (200, 201)


async def test_audit_does_not_roll_back_request(
    app_state: AppState, client: AsyncClient, admin_headers: dict
) -> None:
    resp = await client.post(
        "/api/v1/users/admins",
        headers=admin_headers,
        json={"username": "reseller3", "password": "Reseller-Strong-Pw-123!"},
    )
    assert resp.status_code in (200, 201), resp.text

    async with app_state.db.session() as session:
        created = (
            await session.execute(select(User).where(User.username == "reseller3"))
        ).scalar_one()
    assert created.username == "reseller3"
