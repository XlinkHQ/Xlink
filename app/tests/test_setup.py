"""First-run setup wizard: token-gated, single-use, closed once an admin exists."""

from __future__ import annotations

import asyncio

from httpx import AsyncClient

from app.core.lifespan import AppState
from app.services import setup_service

API = "/api/v1"
PW = "First-Admin-password-1234!"


async def test_setup_flow(app_state: AppState, client: AsyncClient) -> None:
    r = await client.get(f"{API}/setup/status")
    assert r.json() == {"needs_setup": True}
    token = await setup_service.ensure_token(app_state.cache)

    body = {"token": "wrong-token-value", "username": "owner", "password": PW}
    r = await client.post(f"{API}/setup", json=body)
    assert r.status_code in (400, 422)
    # a wrong guess must not burn the real token
    assert await setup_service.ensure_token(app_state.cache) == token

    r = await client.post(f"{API}/setup", json={**body, "token": token, "password": "weak"})
    assert r.status_code in (400, 422)
    assert await setup_service.ensure_token(app_state.cache) == token, "weak pw must not burn token"

    r = await client.post(f"{API}/setup", json={**body, "token": token})
    assert r.status_code == 201, r.text

    r = await client.post(f"{API}/auth/login", json={"identifier": "owner", "password": PW})
    assert r.status_code == 200 and r.json()["user"]["is_sudo"] is True

    assert (await client.get(f"{API}/setup/status")).json() == {"needs_setup": False}
    r = await client.post(f"{API}/setup", json={**body, "token": token, "username": "again"})
    assert r.status_code == 409


async def test_racing_setups_create_one_admin(app_state: AppState, client: AsyncClient) -> None:
    token = await setup_service.ensure_token(app_state.cache)
    results = await asyncio.gather(
        *(
            client.post(
                f"{API}/setup", json={"token": token, "username": f"racer{i}", "password": PW}
            )
            for i in range(5)
        )
    )
    assert sorted(r.status_code for r in results).count(201) == 1
