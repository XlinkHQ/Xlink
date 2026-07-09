from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.user import User, UserExpireStrategy, UserRole

LOGIN = "/api/v1/auth/login"
REGISTER = "/api/v1/auth/register"
USERS = "/api/v1/users"
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


@pytest.fixture
async def admin_headers(app_state: AppState, client: AsyncClient) -> dict[str, str]:
    await _seed_admin(app_state)
    resp = await client.post(LOGIN, json={"identifier": "admin", "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['tokens']['access_token']}"}


async def _create_user(client: AsyncClient, headers: dict, **extra) -> dict:

    body = {"username": "subscriber", **extra}
    resp = await client.post(REGISTER, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["user"]


async def test_expire_strategy_defaults_to_never(client: AsyncClient, admin_headers: dict) -> None:
    user = await _create_user(client, admin_headers)
    assert user["expire_strategy"] == UserExpireStrategy.NEVER
    assert user["on_hold"] is False


async def test_fixed_date_strategy(client: AsyncClient, admin_headers: dict) -> None:
    expire = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    user = await _create_user(client, admin_headers, expire_strategy="fixed_date", expire_at=expire)
    assert user["expire_strategy"] == "fixed_date"
    assert user["on_hold"] is False


async def test_start_on_first_use_sets_on_hold(client: AsyncClient, admin_headers: dict) -> None:
    deadline = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    user = await _create_user(
        client,
        admin_headers,
        expire_strategy="start_on_first_use",
        on_hold_duration_seconds=3600,
        activation_deadline=deadline,
    )

    assert user["expire_strategy"] == "start_on_first_use"
    assert user["on_hold"] is True
    assert user["activation_deadline"] is not None


async def test_legacy_on_hold_still_maps_to_strategy(
    client: AsyncClient, admin_headers: dict
) -> None:
    user = await _create_user(client, admin_headers, on_hold=True)
    assert user["expire_strategy"] == "start_on_first_use"
    assert user["on_hold"] is True


async def test_soft_delete_hides_user_but_keeps_row(
    app_state: AppState, client: AsyncClient, admin_headers: dict
) -> None:
    user = await _create_user(client, admin_headers)
    uid = user["id"]

    resp = await client.delete(f"{USERS}/{uid}", headers=admin_headers)
    assert resp.status_code == 204

    listing = await client.get(USERS, headers=admin_headers, params={"role": "user"})
    assert all(u["id"] != uid for u in listing.json()["items"])

    listing = await client.get(
        USERS, headers=admin_headers, params={"role": "user", "include_removed": True}
    )
    assert any(u["id"] == uid for u in listing.json()["items"])

    async with app_state.db.session() as session:
        import uuid as _uuid

        row = await session.get(User, _uuid.UUID(uid))
        assert row is not None and row.removed is True and row.is_active is False


async def test_soft_deleted_user_cannot_authenticate(
    app_state: AppState, client: AsyncClient, admin_headers: dict
) -> None:
    user = await _create_user(client, admin_headers, password="a-strong-password-1234-AB!")
    await client.delete(f"{USERS}/{user['id']}", headers=admin_headers)
    resp = await client.post(
        LOGIN, json={"identifier": "subscriber", "password": "a-strong-password-1234-AB!"}
    )
    assert resp.status_code == 401


async def test_restore_brings_user_back(client: AsyncClient, admin_headers: dict) -> None:
    user = await _create_user(client, admin_headers)
    uid = user["id"]
    await client.delete(f"{USERS}/{uid}", headers=admin_headers)

    resp = await client.post(f"{USERS}/{uid}/restore", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == uid

    listing = await client.get(USERS, headers=admin_headers, params={"role": "user"})
    assert any(u["id"] == uid for u in listing.json()["items"])


async def test_purge_removes_row(
    app_state: AppState, client: AsyncClient, admin_headers: dict
) -> None:
    user = await _create_user(client, admin_headers)
    uid = user["id"]
    resp = await client.delete(f"{USERS}/{uid}", headers=admin_headers, params={"purge": True})
    assert resp.status_code == 204
    async with app_state.db.session() as session:
        import uuid as _uuid

        assert await session.get(User, _uuid.UUID(uid)) is None


async def test_soft_deleted_username_is_reusable_by_live_user(app_state: AppState) -> None:
    # A soft-deleted user's username/email must free up for a new LIVE user
    # (partial unique index WHERE removed = false), while two LIVE users still
    # can't collide, and lookup resolves to the live row — not the tombstone.
    from app.core.exceptions import ConflictError
    from app.repositories.user import UserRepository
    from app.schemas.user import UserCreate
    from app.services.user_service import UserService

    async with app_state.db.session() as session:
        svc = UserService(UserRepository(session), app_state.cache)

        first = await svc.create(UserCreate(username="reuseme", email="reuse@example.com"))
        await svc.delete(first.id)  # soft delete: removed = True

        # Same username + email now succeeds because the old row is removed.
        second = await svc.create(UserCreate(username="reuseme", email="reuse@example.com"))
        assert second.id != first.id
        await session.flush()

        # Lookup resolves to the LIVE row, not the removed tombstone.
        found = await svc.get_by_identifier("reuseme")
        assert found is not None and found.id == second.id and found.removed is False
        found_by_email = await svc.get_by_identifier("reuse@example.com")
        assert found_by_email is not None and found_by_email.id == second.id

        # Two LIVE users still cannot share a username...
        with pytest.raises(ConflictError):
            await svc.create(UserCreate(username="reuseme", email="other@example.com"))
        # ...nor an email.
        with pytest.raises(ConflictError):
            await svc.create(UserCreate(username="another", email="reuse@example.com"))
