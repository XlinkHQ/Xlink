from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger("xlink.webhooks")


def _is_blocked_ip(raw: str) -> bool:
    ip = ipaddress.ip_address(raw)
    # Unwrap IPv4-mapped IPv6 (::ffff:169.254.169.254) so the class checks
    # below see the real IPv4 address rather than a "public" v6 wrapper.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _assert_public_host(url: str) -> None:
    """Block SSRF to loopback/link-local/private/reserved targets (cloud
    metadata at 169.254.169.254, localhost, internal RFC1918 services)."""
    host = urlparse(url).hostname
    if not host:
        raise ValueError("Webhook URL has no host.")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"Webhook host does not resolve: {host}") from exc
    for info in infos:
        if _is_blocked_ip(info[4][0]):
            raise ValueError(f"Refusing webhook to non-public address: {info[4][0]}")


_ACTION_LABELS: dict[str, str] = {
    "user_created": "🆕 User created",
    "user_updated": "✏️ User updated",
    "user_deleted": "🗑 User deleted",
    "user_limited": "🚫 Data limit reached",
    "user_expired": "⏰ Subscription expired",
    "user_disabled": "⛔️ User disabled",
    "user_enabled": "✅ User enabled",
    "user_data_reset": "♻️ Usage reset",
    "user_expiring_soon": "⏳ Expiring soon",
    "user_data_warning": "📈 Data almost used up",
    "node_down": "🔴 Node down",
    "node_recovered": "🟢 Node recovered",
    "test": "🔔 Test notification",
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError(f"Webhook redirect refused (to {newurl}).")


import http.client


def _guarded_connect(conn: http.client.HTTPConnection) -> None:
    # Close the DNS-rebind TOCTOU: validate the address we ACTUALLY connected to,
    # not just what getaddrinfo returned during the pre-flight check.
    sock = socket.create_connection(
        (conn.host, conn.port), conn.timeout, conn.source_address
    )
    peer = sock.getpeername()[0]
    if _is_blocked_ip(peer):
        sock.close()
        raise ValueError(f"Refusing webhook to non-public address: {peer}")
    conn.sock = sock
    if getattr(conn, "_tunnel_host", None):
        conn._tunnel()


class _GuardedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_guarded_http_conn, req)


class _GuardedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_guarded_https_conn, req)


class _guarded_http_conn(http.client.HTTPConnection):
    connect = _guarded_connect


class _guarded_https_conn(http.client.HTTPSConnection):
    def connect(self) -> None:
        _guarded_connect(self)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


_NO_REDIRECT_OPENER = urllib.request.build_opener(
    _NoRedirect, _GuardedHTTPHandler, _GuardedHTTPSHandler
)


def _post(url: str, payload: dict, headers: dict[str, str], secret: str | None = None) -> None:
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Refusing webhook URL with unsupported scheme: {url}")
    _assert_public_host(url)
    body = json.dumps(payload).encode()
    sent = {"Content-Type": "application/json", **headers}
    if secret:
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        sent["x-webhook-signature"] = f"sha256={signature}"
    req = urllib.request.Request(url, data=body, headers=sent, method="POST")
    # No redirects: a 302 to http://169.254.169.254/ would bypass the
    # pre-flight host check that only validated the original URL.
    with _NO_REDIRECT_OPENER.open(req, timeout=10):
        pass


class WebhookDispatcher:
    def __init__(self, settings: Settings) -> None:
        self._env_urls = list(settings.webhook_urls)
        self._env_discord = settings.discord_webhook_url
        self._env_tg_token = settings.telegram_bot_token
        self._env_tg_chats = list(settings.telegram_chats)
        self._secret = settings.webhook_secret
        self._urls = list(self._env_urls)
        self._discord = self._env_discord
        self._tg_token = self._env_tg_token
        self._tg_chats = list(self._env_tg_chats)
        self._tasks: set[asyncio.Task[None]] = set()

    def apply_overrides(
        self,
        *,
        webhook_address: str = "",
        discord_webhook_url: str = "",
        telegram_bot_token: str = "",
        telegram_chat_ids: str = "",
    ) -> None:
        wa = webhook_address.strip()
        self._urls = (
            [u.strip() for u in wa.split(",") if u.strip()] if wa else list(self._env_urls)
        )
        self._discord = discord_webhook_url.strip() or self._env_discord
        self._tg_token = telegram_bot_token.strip() or self._env_tg_token
        tc = telegram_chat_ids.strip()
        self._tg_chats = (
            [c.strip() for c in tc.split(",") if c.strip()] if tc else list(self._env_tg_chats)
        )

    async def send_test(self) -> None:
        payload = {
            "username": "test",
            "action": "test",
            "detail": "XLink test notification — your channel is configured correctly.",
            "enqueued_at": time.time(),
        }
        await self._send_all(payload)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self._tg_token and self._tg_chats)

    @property
    def enabled(self) -> bool:
        return bool(self._urls or self._discord or self.telegram_enabled)

    async def dispatch(self, action: str, username: str, detail: str | None = None) -> None:
        if not self.enabled:
            return
        payload = {
            "username": username,
            "action": action,
            "detail": detail,
            "enqueued_at": time.time(),
        }
        try:
            task = asyncio.get_running_loop().create_task(self._send_all(payload))
        except RuntimeError:
            await self._send_all(payload)
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def _text(self, payload: dict) -> str:
        label = _ACTION_LABELS.get(payload["action"], payload["action"])
        line = f"{label} — {payload['username']}"
        if payload.get("detail"):
            line += f"\n{payload['detail']}"
        return line

    async def _send_all(self, payload: dict) -> None:
        # Do NOT send the raw secret as a header — _post signs the body with it
        # (x-webhook-signature, HMAC-SHA256). Sending the secret itself would let
        # any receiver forge valid signatures, defeating the scheme.
        headers: dict[str, str] = {}
        for url in self._urls:
            try:
                await asyncio.to_thread(_post, url, payload, headers, self._secret)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                logger.warning("webhook_failed", url=url, error=str(exc))
        if self._discord:
            try:
                await asyncio.to_thread(
                    _post,
                    self._discord,
                    {"content": self._text(payload)},
                    {},
                )
            except (urllib.error.URLError, OSError, ValueError) as exc:
                logger.warning("discord_webhook_failed", error=str(exc))
        if self.telegram_enabled:
            try:
                await self._send_telegram(self._text(payload))
            except Exception as exc:
                logger.warning("telegram_notify_failed", error=str(exc))

    async def _send_telegram(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self._tg_token}/sendMessage"
        for chat_id in self._tg_chats:
            body = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
            try:
                await asyncio.to_thread(_post, url, body, {})
            except (urllib.error.URLError, OSError, ValueError) as exc:
                logger.warning("telegram_notify_failed", chat_id=chat_id, error=str(exc))
