from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_BASE_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"permissions-policy", b"geolocation=(), microphone=(), camera=()"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
)
_HSTS = (b"strict-transport-security", b"max-age=31536000; includeSubDomains; preload")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, production: bool = False) -> None:
        self.app = app
        self._headers = (*_BASE_HEADERS, _HSTS) if production else _BASE_HEADERS

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                existing = {key.lower() for key, _ in headers}
                for key, value in self._headers:
                    if key not in existing:
                        headers.append((key, value))
            await send(message)

        await self.app(scope, receive, send_with_headers)
