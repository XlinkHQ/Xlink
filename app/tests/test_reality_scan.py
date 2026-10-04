"""REALITY target scanner: input parsing, private-address refusal, sudo gate.
Live handshakes are not exercised here (no network in CI)."""

from __future__ import annotations

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
