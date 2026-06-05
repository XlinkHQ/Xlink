from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware


async def ok(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


async def boom(_request: Request) -> JSONResponse:
    raise RuntimeError("explode")


def _client(app: Starlette) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_security_headers_added() -> None:
    app = Starlette(routes=[Route("/", ok)])
    app.add_middleware(SecurityHeadersMiddleware, production=False)
    async with _client(app) as client:
        resp = await client.get("/")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" not in resp.headers


async def test_hsts_only_in_production() -> None:
    app = Starlette(routes=[Route("/", ok)])
    app.add_middleware(SecurityHeadersMiddleware, production=True)
    async with _client(app) as client:
        resp = await client.get("/")
    assert "strict-transport-security" in resp.headers


async def test_security_headers_do_not_override_existing() -> None:
    async def custom(_request: Request) -> JSONResponse:
        return JSONResponse({"ok": True}, headers={"X-Frame-Options": "SAMEORIGIN"})

    app = Starlette(routes=[Route("/", custom)])
    app.add_middleware(SecurityHeadersMiddleware, production=False)
    async with _client(app) as client:
        resp = await client.get("/")
    assert resp.headers["x-frame-options"] == "SAMEORIGIN"


async def test_request_id_generated_when_absent() -> None:
    app = Starlette(routes=[Route("/", ok)])
    app.add_middleware(RequestContextMiddleware)
    async with _client(app) as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.headers["x-request-id"]


async def test_request_id_propagated_from_header() -> None:
    app = Starlette(routes=[Route("/", ok)])
    app.add_middleware(RequestContextMiddleware)
    async with _client(app) as client:
        resp = await client.get("/", headers={"X-Request-ID": "abc123"})
    assert resp.headers["x-request-id"] == "abc123"


async def test_request_context_reraises_errors() -> None:
    app = Starlette(routes=[Route("/", boom)])
    app.add_middleware(RequestContextMiddleware)
    async with _client(app) as client:
        try:
            await client.get("/")
        except RuntimeError as exc:
            assert str(exc) == "explode"
        else:
            raise AssertionError("expected RuntimeError to propagate")
