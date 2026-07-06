from __future__ import annotations

from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger
from app.middleware.headers import find_header

logger = get_logger("xlink.ratelimit")

IPAddress = IPv4Address | IPv6Address
IPNetwork = IPv4Network | IPv6Network

_EXCLUDED_PATH_MARKERS = ("/health/", "/health", "/ready")
_WINDOW_SECONDS = 60

# Auth endpoints get a much tighter, fail-closed limit to blunt credential
# brute-force. Keyed per-IP + per-path (not shared with the coarse method bucket).
_AUTH_PATH_MARKERS = ("/auth/login", "/auth/refresh", "/auth/register")
_AUTH_LIMIT = 10


def is_auth_path(path: str) -> bool:
    return any(marker in path for marker in _AUTH_PATH_MARKERS)


def parse_proxy_networks(values: list[str]) -> tuple[IPNetwork, ...]:
    return tuple(ip_network(value, strict=False) for value in values)


def parse_forwarded_for(value: str) -> list[IPAddress]:
    forwarded_for = [item.strip() for item in value.split(",")]
    if not forwarded_for or any(not item for item in forwarded_for):
        raise ValueError("empty X-Forwarded-For entry")
    return [ip_address(item) for item in forwarded_for]


def is_trusted_proxy(host: str | None, trusted_proxies: tuple[IPNetwork, ...]) -> bool:
    if not host or not trusted_proxies:
        return False
    try:
        peer = ip_address(host)
    except ValueError:
        return False
    return any(peer in network for network in trusted_proxies)


def _peer_host(scope: Scope) -> str | None:
    client = scope.get("client")
    return client[0] if client else None


def resolve_client_ip(scope: Scope, trusted_proxies: tuple[IPNetwork, ...]) -> str:
    peer_host = _peer_host(scope)
    if not is_trusted_proxy(peer_host, trusted_proxies):
        return peer_host or "unknown"

    forwarded_for = find_header(scope.get("headers", []), b"x-forwarded-for")
    if not forwarded_for:
        return peer_host or "unknown"

    forwarded_chain = parse_forwarded_for(forwarded_for)
    for ip in reversed(forwarded_chain):
        if not is_trusted_proxy(str(ip), trusted_proxies):
            return str(ip)
    return str(forwarded_chain[0])


def _normalize_path(path: str) -> str:
    # Collapse id-like segments (UUIDs, numbers) to a placeholder so a client
    # can't evade the per-route limit by varying the id, and the keyspace stays
    # bounded to the number of real routes rather than one bucket per id. The
    # route template isn't available at outer-middleware time, so approximate it.
    out = []
    for seg in path.split("/"):
        if not seg:
            continue
        if seg.isdigit() or (len(seg) >= 16 and any(c.isdigit() for c in seg) and "-" in seg):
            out.append(":id")
        else:
            out.append(seg)
    return "/" + "/".join(out)


def route_rate_limit_key(scope: Scope) -> str:
    # Route-aware: method + normalized path, so a flood on one route doesn't
    # exhaust the shared bucket for every other route from the same IP.
    return f"{scope.get('method', '')}:{_normalize_path(scope.get('path', ''))}"


def is_excluded_path(path: str) -> bool:
    return any(marker in path for marker in _EXCLUDED_PATH_MARKERS)


async def incr_window(redis, key: str) -> int:
    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, _WINDOW_SECONDS, nx=True)
        results = await pipe.execute()
    return int(results[0])


async def _send_json(send: Send, status: int, code: str, message: str, headers=None) -> None:
    import orjson

    raw = orjson.dumps({"error": {"code": code, "message": message}})
    response_headers = [(b"content-type", b"application/json")]
    if headers:
        response_headers.extend(headers)
    await send({"type": "http.response.start", "status": status, "headers": response_headers})
    await send({"type": "http.response.body", "body": raw})


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        limit_per_minute: int,
        enabled: bool = True,
        fail_open: bool = True,
        trusted_proxy_ips: list[str] | None = None,
    ) -> None:
        self.app = app
        self._limit = limit_per_minute
        self._enabled = enabled
        self._fail_open = fail_open
        self._trusted_proxies = parse_proxy_networks(trusted_proxy_ips or [])

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._enabled:
            await self.app(scope, receive, send)
            return

        if is_excluded_path(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        state = getattr(scope.get("app").state, "xlink", None) if scope.get("app") else None
        if state is None:
            await self.app(scope, receive, send)
            return

        try:
            client_ip = resolve_client_ip(scope, self._trusted_proxies)
        except ValueError:
            await _send_json(send, 400, "invalid_forwarded_for", "Invalid X-Forwarded-For header.")
            return

        auth_path = is_auth_path(scope.get("path", ""))
        if auth_path:
            key = f"rl:auth:{client_ip}:{scope.get('path', '')}"
            limit = _AUTH_LIMIT
        else:
            key = f"rl:{client_ip}:{route_rate_limit_key(scope)}"
            limit = self._limit
        redis = state.cache.client
        try:
            count = await incr_window(redis, key)
        except Exception:
            # Auth endpoints fail CLOSED: a limiter outage must not open the door
            # to unlimited credential brute-force.
            await self._handle_redis_failure(scope, receive, send, force_closed=auth_path)
            return

        if count > limit:
            logger.warning(
                "rate_limited", client_ip=client_ip, route=route_rate_limit_key(scope), count=count
            )
            await _send_json(
                send,
                429,
                "rate_limited",
                "Too many requests.",
                headers=[(b"retry-after", b"60")],
            )
            return

        remaining = str(max(0, limit - count)).encode("latin-1")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((b"x-ratelimit-limit", str(limit).encode("latin-1")))
                headers.append((b"x-ratelimit-remaining", remaining))
            await send(message)

        await self.app(scope, receive, send_with_headers)

    async def _handle_redis_failure(
        self, scope: Scope, receive: Receive, send: Send, *, force_closed: bool = False
    ) -> None:
        logger.warning("rate_limit_redis_unavailable", fail_open=self._fail_open and not force_closed)
        if self._fail_open and not force_closed:
            await self.app(scope, receive, send)
            return
        await _send_json(send, 503, "rate_limit_unavailable", "Rate limiter unavailable.")
