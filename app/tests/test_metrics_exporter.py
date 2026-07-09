from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.core.lifespan import AppState
from app.main import create_app

_TOKEN = "test-metrics-scrape-token-value"


def _client_for(state: AppState) -> AsyncClient:
    app = create_app(state.settings)
    app.state.xlink = state
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
async def metrics_client(app_state: AppState) -> AsyncIterator[AsyncClient]:
    # Opt in: set the scrape token so GET /metrics is enabled.
    app_state.settings.metrics_token = SecretStr(_TOKEN)
    async with _client_for(app_state) as ac:
        yield ac


async def test_metrics_disabled_without_token(client: AsyncClient) -> None:
    # Default conftest client has no metrics_token -> endpoint is 404.
    resp = await client.get("/metrics")
    assert resp.status_code == 404


async def test_metrics_requires_bearer(metrics_client: AsyncClient) -> None:
    # Enabled but no/incorrect credentials -> 401.
    resp = await metrics_client.get("/metrics")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"

    bad = await metrics_client.get("/metrics", headers={"Authorization": "Bearer wrong"})
    assert bad.status_code == 401


async def test_metrics_returns_prometheus_text(metrics_client: AsyncClient) -> None:
    resp = await metrics_client.get(
        "/metrics", headers={"Authorization": f"Bearer {_TOKEN}"}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    # Prometheus exposition format: HELP/TYPE lines and our namespaced series.
    assert "# HELP" in body
    assert "# TYPE" in body
    assert "xlink_http_requests_total" in body
    assert "xlink_http_request_duration_seconds" in body


async def test_request_metrics_increment(metrics_client: AsyncClient) -> None:
    def _scrape_count(text: str, route: str) -> float:
        total = 0.0
        for line in text.splitlines():
            if line.startswith("xlink_http_requests_total{") and f'route="{route}"' in line:
                total += float(line.rsplit(" ", 1)[1])
        return total

    # Drive a known route (the liveness probe) a few times.
    for _ in range(3):
        r = await metrics_client.get("/api/v1/health/live")
        assert r.status_code == 200

    scrape = await metrics_client.get(
        "/metrics", headers={"Authorization": f"Bearer {_TOKEN}"}
    )
    count = _scrape_count(scrape.text, "/api/v1/health/live")
    assert count >= 3.0

    # Cardinality control: the route label is the template, so a UUID-ish path
    # never appears verbatim as its own series.
    assert "route=\"/api/v1/health/live\"" in scrape.text
