from __future__ import annotations

import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.middleware.audit_writer import AuditEntry

_AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_SKIP_PREFIXES = ("/api/v1/agent/", "/api/v1/auth/refresh")
_SKIP_SUFFIXES = (
    "/traffic/users/usage",
    "/traffic/users/last-seen",
)
_KNOWN_ACTIONS = {
    "confirm",
    "enroll",
    "disable",
    "enable",
    "demote",
    "promote",
    "reset",
    "restore",
    "revoke-subscription",
    "restart",
    "restart-core",
    "disable-users",
    "enable-users",
    "change-password",
    "import-db",
    "commit",
    "diff",
    "plan",
    "execute",
    "run",
    "cleanup",
    "export",
    "logout-all",
    "ping",
    "import",
    "usage",
    "last-seen",
    "test",
    "bulk",
    "failover",
    "heartbeat",
    "agent-token",
    "rotate",
    "sync",
}


def _looks_like_id(seg: str) -> bool:
    if seg.isdigit():
        return True
    return len(seg) >= 16 and "-" in seg and any(c.isdigit() for c in seg)


def _action_for(method: str, path: str) -> str:
    parts = [p for p in path.split("/") if p and p not in ("api", "v1")]
    if not parts:
        return method.lower() + " request"
    named = [p for p in parts if not _looks_like_id(p)]
    verb = {"POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}.get(
        method, method.lower()
    )
    if named and named[-1] in _KNOWN_ACTIONS:
        verb = named[-1]
        resource = "/".join(named[:-1]) or named[-1]
    else:
        resource = "/".join(named) or "request"
    return f"{verb} {resource}"


class AuditMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        method = scope["method"]
        path = scope["path"]
        if (
            method not in _AUDITED_METHODS
            or any(path.startswith(p) for p in _SKIP_PREFIXES)
            or any(path.endswith(s) for s in _SKIP_SUFFIXES)
        ):
            await self._app(scope, receive, send)
            return

        status_code = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        await self._app(scope, receive, send_wrapper)

        if status_code >= 400:
            return

        actor_id = scope.get("state", {}).get("actor_id")
        if not actor_id:
            return
        if isinstance(actor_id, str):
            try:
                actor_id = uuid.UUID(actor_id)
            except ValueError:
                return
        actor_username = scope.get("state", {}).get("actor_username", "")

        app_state = scope.get("app")
        xlink = getattr(getattr(app_state, "state", None), "xlink", None)
        writer = getattr(xlink, "audit_writer", None)
        if writer is None:
            return

        client_host = ""
        client = scope.get("client")
        if client:
            client_host = client[0]
        writer.submit(
            AuditEntry(
                actor_id=actor_id,
                actor_username=actor_username,
                method=method,
                path=path[:512],
                action=_action_for(method, path),
                status_code=status_code,
                ip_address=client_host[:64],
            )
        )
