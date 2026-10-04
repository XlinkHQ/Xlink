"""REALITY target scanner: input parsing, private-address refusal, sudo gate.
Live handshakes are not exercised here (no network in CI)."""

from __future__ import annotations

import uuid as uuid_mod

import pytest
from httpx import AsyncClient

from app.services import reality_scan


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("www.microsoft.com", ("www.microsoft.com", 443)),
        ("https://Dl.Google.com/path", ("dl.google.com", 443)),
        ("example.com:8443", ("example.com", 8443)),
    ],
)
def test_parse_target(raw: str, want: tuple[str, int]) -> None:
    assert reality_scan.parse_target(raw) == want


@pytest.mark.parametrize("raw", ["1.1.1.1", "example.com:0", "example.com:x", ""])
def test_parse_target_rejects(raw: str) -> None:
    with pytest.raises(ValueError):
        reality_scan.parse_target(raw)


async def test_private_targets_are_refused() -> None:
    (r,) = await reality_scan.scan(["localhost"])
    assert not r.ok and r.problems == ["resolves to a non-public address"]


async def test_scan_endpoint_requires_sudo(client: AsyncClient) -> None:
    r = await client.post("/api/v1/reality/scan", json={"targets": ["example.com"]})
    assert r.status_code == 401


async def test_node_scan_round_trip(app_state, client: AsyncClient) -> None:  # noqa: ANN001
    """Queue a scan on a node, let the 'agent' report, read the result back."""
    from app.agent.domain import CommandStatus, NodeCommand
    from app.core.security import hash_password
    from app.domain.node import Node, NodeStatus
    from app.domain.user import User, UserRole

    pw = "Sudo-admin-password-1234-AB!"
    async with app_state.db.session() as s:
        s.add(
            User(
                username="root",
                hashed_password=hash_password(pw),
                role=UserRole.ADMIN,
                is_sudo=True,
            )
        )
        node = Node(
            name="n",
            slug="n-scan",
            host="1.2.3.4",
            port=443,
            status=NodeStatus.ACTIVE,
            node_metadata={"agent_token_hash": "h"},
        )
        s.add(node)
        await s.flush()
        node_id = node.id
    r = await client.post("/api/v1/auth/login", json={"identifier": "root", "password": pw})
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}

    r = await client.post(
        f"/api/v1/reality/scan/node/{node_id}", headers=h, json={"targets": ["a.com"]}
    )
    if r.status_code == 503:  # command signing not configured in this env
        pytest.skip("node commands disabled")
    assert r.status_code == 202, r.text
    cid = r.json()["command_id"]
    assert (await client.get(f"/api/v1/reality/scan/commands/{cid}", headers=h)).json()[
        "status"
    ] == "pending"

    async with app_state.db.session() as s:
        cmd = await s.get(NodeCommand, uuid_mod.UUID(cid))
        cmd.status = CommandStatus.SUCCEEDED
        cmd.result = {
            "results": [
                {
                    "target": "a.com",
                    "port": 443,
                    "ip": "1.1.1.1",
                    "ok": True,
                    "tls13": True,
                    "h2": True,
                    "x25519": True,
                    "cert_valid": True,
                    "latency_ms": 12.0,
                    "issuer": "X",
                    "problems": [],
                }
            ]
        }
    body = (await client.get(f"/api/v1/reality/scan/commands/{cid}", headers=h)).json()
    assert body["status"] == "succeeded" and body["results"][0]["ok"] is True
