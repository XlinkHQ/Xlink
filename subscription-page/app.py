"""XLink standalone subscription-page forwarder.

A tiny public-facing service that serves user subscription links WITHOUT
exposing the panel's own domain. It receives the public ``GET /sub/{token}``
request, forwards it to the panel's INTERNAL subscription endpoint over the
private network, and streams the panel's response (config feed or status page)
back to the client.

Why this exists
---------------
With this service in front, the panel API can be locked down / IP-restricted
(only this container is allowed to reach it) while subscription links keep
resolving on a separate, throwaway domain. Same model as Remnawave's separate
subscription page: the sub-page talks to the panel over the internal network
and the panel stays private.

What it must preserve for the panel to behave correctly
-------------------------------------------------------
The panel's ``/sub/{token}`` handler depends on a few request signals:

* ``User-Agent``   -> VPN-client detection + feed format selection.
* ``x-hwid``       -> per-device (HWID) device-limit tracking.
* real client IP   -> device-limit IP tracking + rate limiting. Forwarded via
                      ``X-Forwarded-For`` (this proxy appends the peer IP to any
                      existing chain). NOTE: for the panel to read this as the
                      client IP, the panel's uvicorn must trust this container
                      as a proxy (``--forwarded-allow-ips``); see README.
* Host             -> the panel derives the subscription URL BASE it advertises
                      (``profile-web-page-url`` header, status-page ``sub_url``)
                      from ``X-Forwarded-Host`` / ``Host``. We set
                      ``X-Forwarded-Host`` to this service's PUBLIC host so the
                      panel advertises the sub-page domain, never its own.

The service is deliberately dependency-light: FastAPI + httpx + uvicorn, which
are already part of the XLink stack.
"""

from __future__ import annotations

import os
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response

# ─────────────────────────────────────────────────────────────
# Configuration (env-driven; sane defaults for the compose network)
# ─────────────────────────────────────────────────────────────

# Internal base URL of the panel API, reachable over the private compose /
# k8s network only (e.g. http://api:8000). The panel itself need not be
# publicly exposed at all.
PANEL_INTERNAL_URL = os.environ.get("PANEL_INTERNAL_URL", "http://api:8000").rstrip("/")

# Path prefix the panel mounts its API under (matches XLINK_API_V1_PREFIX).
API_V1_PREFIX = os.environ.get("PANEL_API_V1_PREFIX", "/api/v1").rstrip("/")

# The PUBLIC host clients use to reach THIS service (e.g. sub.example.com).
# When set, it is forwarded to the panel as X-Forwarded-Host so the panel
# advertises subscription URLs on the sub-page domain instead of its own.
# Leave empty to pass the incoming Host through unchanged (works when this
# service is itself behind a TLS edge that already sets a correct Host).
PUBLIC_HOST = os.environ.get("SUB_PAGE_PUBLIC_HOST", "").strip()

# Scheme clients use to reach this service. Forwarded as X-Forwarded-Proto so
# the panel builds https:// subscription URLs behind a TLS edge.
PUBLIC_PROTO = os.environ.get("SUB_PAGE_PUBLIC_PROTO", "https").strip() or "https"

# Optional shared secret sent to the panel as X-Sub-Page-Token. The panel does
# NOT require it today (the signed URL token already authenticates the request),
# but it lets an operator add a panel-side allow rule later without changing
# this service. Sent only when configured.
PANEL_API_TOKEN = os.environ.get("PANEL_API_TOKEN", "").strip()

# Upstream request timeout (seconds).
UPSTREAM_TIMEOUT = float(os.environ.get("SUB_PAGE_TIMEOUT", "30"))


# Hop-by-hop headers must never be forwarded (RFC 7230 §6.1). httpx sets its
# own Host/Content-Length; we drop the client's Host so our explicit
# X-Forwarded-Host wins and httpx targets the panel correctly.
_DROP_REQUEST_HEADERS = {
    "host",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "content-length",
}

_DROP_RESPONSE_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "content-encoding",  # httpx already decoded the body; length/encoding differ
}


app = FastAPI(
    title="XLink Subscription Page",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# One shared client (connection pooling). Do NOT let httpx auto-follow
# redirects — pass the panel's response through verbatim.
_client: httpx.AsyncClient | None = None


@app.on_event("startup")
async def _startup() -> None:
    global _client
    _client = httpx.AsyncClient(
        base_url=PANEL_INTERNAL_URL,
        timeout=UPSTREAM_TIMEOUT,
        follow_redirects=False,
    )


@app.on_event("shutdown")
async def _shutdown() -> None:
    if _client is not None:
        await _client.aclose()


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _build_forward_headers(request: Request) -> dict[str, str]:
    """Copy client headers, preserving the signals the panel needs.

    - Passes User-Agent and x-hwid straight through.
    - Appends the real peer IP to X-Forwarded-For (chains any existing value).
    - Overrides X-Forwarded-Host / -Proto so the panel advertises the sub-page
      public domain in the subscription URLs it returns.
    """
    headers: dict[str, str] = {}
    for key, value in request.headers.items():
        if key.lower() in _DROP_REQUEST_HEADERS:
            continue
        headers[key] = value

    peer_ip = _client_ip(request)
    existing_xff = request.headers.get("x-forwarded-for")
    if peer_ip:
        headers["X-Forwarded-For"] = f"{existing_xff}, {peer_ip}" if existing_xff else peer_ip
    elif existing_xff:
        headers["X-Forwarded-For"] = existing_xff

    # Advertise the sub-page domain, never the panel's.
    public_host = PUBLIC_HOST or request.headers.get("host", "")
    if public_host:
        headers["X-Forwarded-Host"] = public_host
    headers["X-Forwarded-Proto"] = (
        request.headers.get("x-forwarded-proto") or PUBLIC_PROTO
    )

    if PANEL_API_TOKEN:
        headers["X-Sub-Page-Token"] = PANEL_API_TOKEN

    return headers


async def _forward(request: Request, token: str, fmt: str | None = None) -> Response:
    assert _client is not None, "http client not initialised"

    target_path = f"{API_V1_PREFIX}/subscriptions/sub/{token}"
    params = list(request.query_params.multi_items())
    # A trailing /{fmt} path segment maps to the ?format= query the panel reads.
    # An explicit ?format= in the query always wins.
    if fmt and "format" not in request.query_params:
        params.append(("format", fmt))
    query = urlencode(params)
    url = f"{target_path}?{query}" if query else target_path

    try:
        upstream = await _client.get(url, headers=_build_forward_headers(request))
    except httpx.HTTPError:
        # Panel unreachable / timed out. Do not leak internal details.
        return Response(status_code=502, content=b"Bad Gateway", media_type="text/plain")

    resp_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() not in _DROP_RESPONSE_HEADERS
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=resp_headers,
        media_type=upstream.headers.get("content-type"),
    )


# Public routes. Both the plain and the /{fmt} variant map to the panel's
# single /sub/{token} endpoint; a trailing format segment is passed through as
# the ?format= query param the panel already understands.
@app.get("/sub/{token}", include_in_schema=False)
async def sub(request: Request, token: str) -> Response:
    return await _forward(request, token)


@app.get("/sub/{token}/{fmt}", include_in_schema=False)
async def sub_with_format(request: Request, token: str, fmt: str) -> Response:
    return await _forward(request, token, fmt=fmt)
