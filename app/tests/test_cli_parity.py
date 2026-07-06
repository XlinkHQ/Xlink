from __future__ import annotations

import uuid

from pydantic import SecretStr

from app.cli.runner import run_cli
from app.core.lifespan import AppState
from app.core.security import hash_password, verify_password
from app.domain.user import User, UserRole
from app.repositories.user import UserRepository


async def _cli(app_state: AppState, command: str, **overrides) -> str:

    base = {"admin_username": None, "admin_password": None}
    base.update(overrides)
    if isinstance(base.get("admin_password"), str):
        base["admin_password"] = SecretStr(base["admin_password"])
    settings = app_state.settings.model_copy(update=base)
    async with app_state.db.session() as session:
        return await run_cli(session, app_state.cache, settings, command)


async def _seed_admin(app_state: AppState, *, is_sudo: bool = True, username: str | None = None):
    username = username or f"adm-{uuid.uuid4().hex[:6]}"
    async with app_state.db.session() as session:
        admin = User(
            username=username,
            hashed_password=hash_password("Strong-Password-1234!"),
            role=UserRole.ADMIN,
            is_sudo=is_sudo,
        )
        session.add(admin)
        await session.flush()
        return username, admin.id


async def _seed_user(app_state: AppState, *, username: str | None = None, owner_id=None):
    username = username or f"usr-{uuid.uuid4().hex[:6]}"
    async with app_state.db.session() as session:
        user = User(
            username=username,
            hashed_password=hash_password("Strong-Password-1234!"),
            role=UserRole.USER,
            owner_id=owner_id,
        )
        session.add(user)
        await session.flush()
        return username, user.id


async def test_admin_create_sudo_default(app_state: AppState):
    out = await _cli(app_state, "admin create -u newadmin -p Strong-Password-1234!")
    assert "created (sudo)" in out
    async with app_state.db.session() as session:
        admin = await UserRepository(session).get_by_username("newadmin")
        assert admin is not None and admin.is_sudo is True


async def test_admin_create_reseller(app_state: AppState):
    out = await _cli(app_state, "admin create -u reseller1 -p Strong-Password-1234! --no-sudo")
    assert "reseller" in out
    async with app_state.db.session() as session:
        admin = await UserRepository(session).get_by_username("reseller1")
        assert admin is not None and admin.is_sudo is False


async def test_admin_create_password_from_env(app_state: AppState):
    out = await _cli(
        app_state,
        "admin create -u envadmin",
        admin_password="Env-Strong-Password-99!",
    )
    assert "created" in out


async def test_admin_create_missing_password(app_state: AppState):
    out = await _cli(app_state, "admin create -u noproblem")
    assert "password is required" in out


async def test_admin_update_password_and_sudo(app_state: AppState):
    username, _ = await _seed_admin(app_state, is_sudo=True)
    out = await _cli(app_state, f"admin update -u {username} -p New-Strong-Password-55! --no-sudo")
    assert "updated" in out
    async with app_state.db.session() as session:
        admin = await UserRepository(session).get_by_username(username)
        assert admin.is_sudo is False
        assert verify_password("New-Strong-Password-55!", admin.hashed_password)


async def test_admin_import_from_env(app_state: AppState):
    out = await _cli(
        app_state,
        "admin import-from-env",
        admin_username="bootadmin",
        admin_password="Boot-Strong-Password-99!",
    )
    assert "from env" in out
    async with app_state.db.session() as session:
        admin = await UserRepository(session).get_by_username("bootadmin")
        assert admin is not None and admin.is_sudo is True


async def test_admin_delete_requires_yes(app_state: AppState):
    username, _ = await _seed_admin(app_state)
    out = await _cli(app_state, f"admin delete -u {username}")
    assert "refusing" in out
    out = await _cli(app_state, f"admin delete -u {username} --yes")
    assert "deleted" in out


async def test_user_set_owner(app_state: AppState):
    admin_name, admin_id = await _seed_admin(app_state)
    user_name, _ = await _seed_user(app_state)
    out = await _cli(app_state, f"user set-owner -u {user_name} --owner {admin_name}")
    assert "owner set to" in out
    async with app_state.db.session() as session:
        user = await UserRepository(session).get_by_username(user_name)
        assert user.owner_id == admin_id


async def test_user_set_owner_transfer_needs_yes(app_state: AppState):
    a1, a1_id = await _seed_admin(app_state)
    a2, a2_id = await _seed_admin(app_state)
    user_name, _ = await _seed_user(app_state, owner_id=a1_id)
    out = await _cli(app_state, f"user set-owner -u {user_name} --owner {a2}")
    assert "already owned" in out
    out = await _cli(app_state, f"user set-owner -u {user_name} --owner {a2} --yes")
    assert "owner set to" in out
    async with app_state.db.session() as session:
        user = await UserRepository(session).get_by_username(user_name)
        assert user.owner_id == a2_id


async def test_user_list_filter_by_owner(app_state: AppState):
    admin_name, admin_id = await _seed_admin(app_state)
    owned, _ = await _seed_user(app_state, owner_id=admin_id)
    other, _ = await _seed_user(app_state)
    out = await _cli(app_state, f"user list --owner {admin_name}")
    assert owned in out
    assert other not in out


async def test_user_delete_requires_yes(app_state: AppState):
    user_name, _ = await _seed_user(app_state)
    out = await _cli(app_state, f"user delete -u {user_name}")
    assert "refusing" in out
    out = await _cli(app_state, f"user delete -u {user_name} --yes")
    assert "deleted" in out


async def test_sub_link_and_config(app_state: AppState):
    user_name, _ = await _seed_user(app_state)
    link = await _cli(app_state, f"sub link -u {user_name}")
    assert "/subscriptions/sub/" in link

    cfg = await _cli(app_state, f"sub config -u {user_name} -f clash")
    assert "error" not in cfg.lower()
