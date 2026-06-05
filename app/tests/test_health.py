from __future__ import annotations

from httpx import AsyncClient


async def test_liveness(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readiness(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["dependencies"] == {"database": True, "redis": True}


async def test_request_id_header_present(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live")
    assert "X-Request-ID" in resp.headers


async def test_security_headers_present(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
