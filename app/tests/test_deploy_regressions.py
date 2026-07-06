from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import Settings
from app.core.lifespan import AppState
from app.core.security import hash_password
from app.domain.user import User, UserRole

LOGIN = "/api/v1/auth/login"
ADMIN_PASSWORD = "admin-strong-password-1234-AB!"


def test_csv_env_parsing_accepts_plain_strings():
    s = Settings(
        database_url_override="sqlite+aiosqlite:///:memory:",
        cors_origins="http://a.com,http://b.com",
        trusted_hosts="x.com,localhost",
    )
    assert s.cors_origins == ["http://a.com", "http://b.com"]
    assert s.trusted_hosts == ["x.com", "localhost"]


def test_csv_env_parsing_accepts_empty():
    s = Settings(database_url_override="sqlite+aiosqlite:///:memory:", cors_origins="")
    assert s.cors_origins == []


def test_node_offline_knobs_configurable():
    s = Settings(
        database_url_override="sqlite+aiosqlite:///:memory:",
        node_offline_after_seconds=30,
        node_status_interval_seconds=10,
    )
    assert s.node_offline_after_seconds == 30
    assert s.node_status_interval_seconds == 10


def test_os_release_reads_host_mount(tmp_path, monkeypatch):
    from app.api.v1.routers import monitoring

    host = tmp_path / "os-release"
    host.write_text('PRETTY_NAME="Ubuntu 24.04 LTS"\nID=ubuntu\n')
    real_open = open

    def fake_open(path, *a, **k):
        if path == "/host/os-release":
            return real_open(host, *a, **k)
        if path == "/etc/os-release":
            raise FileNotFoundError
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", fake_open)
    assert monitoring._os_pretty_name() == "Ubuntu 24.04 LTS"
    assert monitoring._os_slug() == "ubuntu"


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
async def sudo_headers(app_state: AppState, client: AsyncClient) -> dict[str, str]:
    await _seed_admin(app_state)
    resp = await client.post(LOGIN, json={"identifier": "admin", "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['tokens']['access_token']}"}


async def test_sudo_admin_can_create_admin(client: AsyncClient, sudo_headers: dict) -> None:
    resp = await client.post(
        "/api/v1/users/admins",
        headers=sudo_headers,
        json={"username": "reseller9", "password": "Reseller-Strong-Pw-11!", "is_sudo": False},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["username"] == "reseller9"
