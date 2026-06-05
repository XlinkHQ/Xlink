from __future__ import annotations

from types import SimpleNamespace

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.middleware.rate_limit import (
    RateLimitMiddleware,
    is_excluded_path,
    parse_forwarded_for,
    parse_proxy_networks,
)


class FailingRedis:
    def pipeline(self, transaction: bool = True):
        raise RuntimeError("redis unavailable")


async def one(_request: Request) -> JSONResponse:
    return JSONResponse({"route": "one"})


async def two(_request: Request) -> JSONResponse:
    return JSONResponse({"route": "two"})


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"route": "health"})


def _app(redis, *, fail_open: bool = True, limit: int = 1) -> Starlette:
    app = Starlette(
        routes=[
            Route("/one", one),
            Route("/two", two),
            Route("/api/v1/health/live", health),
        ]
    )
    app.state.xlink = SimpleNamespace(cache=SimpleNamespace(client=redis))
    app.add_middleware(
        RateLimitMiddleware,
        limit_per_minute=limit,
        trusted_proxy_ips=["10.0.0.0/8"],
        fail_open=fail_open,
    )
    return app


def _fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=False)


def test_forwarded_for_rejects_malformed_values() -> None:
    for value in ("", "203.0.113.1,", "not-an-ip"):
        with pytest.raises(ValueError):
            parse_forwarded_for(value)


def test_proxy_networks_support_cidr_ranges() -> None:
    networks = parse_proxy_networks(["10.0.0.0/8", "127.0.0.1"])
    assert len(networks) == 2


def test_excluded_paths() -> None:
    assert is_excluded_path("/api/v1/health/live")
    assert is_excluded_path("/api/v1/health/ready")
    assert not is_excluded_path("/api/v1/users")


async def test_health_path_is_never_rate_limited() -> None:
    redis = _fake_redis()
    app = _app(redis, limit=1)
    transport = ASGITransport(app=app, client=("198.51.100.7", 123))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(5):
            resp = await client.get("/api/v1/health/live")
            assert resp.status_code == 200
    keys = await redis.keys("rl:*")
    assert keys == []


async def test_rate_limit_uses_trusted_forwarded_for_client_ip() -> None:
    redis = _fake_redis()
    app = _app(redis)
    transport = ASGITransport(app=app, client=("10.1.2.3", 123))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/one", headers={"X-Forwarded-For": "203.0.113.9"})
    assert response.status_code == 200
    keys = [k.decode() for k in await redis.keys("rl:*")]
    assert any(k.startswith("rl:203.0.113.9:GET:/one") for k in keys)


async def test_rate_limit_ignores_forwarded_for_from_untrusted_peer() -> None:
    redis = _fake_redis()
    app = _app(redis)
    transport = ASGITransport(app=app, client=("198.51.100.7", 123))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/one", headers={"X-Forwarded-For": "203.0.113.9"})
    assert response.status_code == 200
    keys = [k.decode() for k in await redis.keys("rl:*")]
    assert any(k.startswith("rl:198.51.100.7:GET:/one") for k in keys)


async def test_rate_limit_rejects_bad_forwarded_for_from_trusted_proxy() -> None:
    redis = _fake_redis()
    app = _app(redis)
    transport = ASGITransport(app=app, client=("10.1.2.3", 123))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/one", headers={"X-Forwarded-For": "bad-ip"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_forwarded_for"


async def test_rate_limit_is_route_aware() -> None:
    redis = _fake_redis()
    app = _app(redis, limit=1)
    transport = ASGITransport(app=app, client=("198.51.100.7", 123))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.get("/one")
        second = await client.get("/one")
        third = await client.get("/two")
    assert first.status_code == 200
    assert second.status_code == 429
    assert third.status_code == 200


async def test_rate_limit_sets_headers() -> None:
    redis = _fake_redis()
    app = _app(redis, limit=5)
    transport = ASGITransport(app=app, client=("198.51.100.7", 123))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/one")
    assert resp.headers["x-ratelimit-limit"] == "5"
    assert resp.headers["x-ratelimit-remaining"] == "4"


async def test_single_round_trip_uses_pipeline() -> None:
    redis = _fake_redis()
    calls = {"pipeline": 0}
    original = redis.pipeline

    def counting_pipeline(*args, **kwargs):
        calls["pipeline"] += 1
        return original(*args, **kwargs)

    redis.pipeline = counting_pipeline
    app = _app(redis, limit=10)
    transport = ASGITransport(app=app, client=("198.51.100.7", 123))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/one")
    assert calls["pipeline"] == 1


async def test_rate_limit_redis_failure_can_fail_open() -> None:
    app = _app(FailingRedis(), fail_open=True)
    transport = ASGITransport(app=app, client=("198.51.100.7", 123))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/one")
    assert response.status_code == 200


async def test_rate_limit_redis_failure_can_fail_closed() -> None:
    app = _app(FailingRedis(), fail_open=False)
    transport = ASGITransport(app=app, client=("198.51.100.7", 123))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/one")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "rate_limit_unavailable"
