from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger("xlink.webhooks")


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
}


def _post(url: str, payload: dict, headers: dict[str, str]) -> None:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json", **headers}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=10):
        pass


class WebhookDispatcher:
    def __init__(self, settings: Settings) -> None:
        self._urls = settings.webhook_urls
        self._secret = settings.webhook_secret
        self._discord = settings.discord_webhook_url
        self._tg_token = settings.telegram_bot_token
        self._tg_chats = settings.telegram_chats
        self._tasks: set[asyncio.Task[None]] = set()

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
        headers = {"x-webhook-secret": self._secret} if self._secret else {}
        for url in self._urls:
            try:
                await asyncio.to_thread(_post, url, payload, headers)
            except (urllib.error.URLError, OSError) as exc:
                logger.warning("webhook_failed", url=url, error=str(exc))
        if self._discord:
            try:
                await asyncio.to_thread(
                    _post,
                    self._discord,
                    {"content": self._text(payload)},
                    {},
                )
            except (urllib.error.URLError, OSError) as exc:
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
            except (urllib.error.URLError, OSError) as exc:
                logger.warning("telegram_notify_failed", chat_id=chat_id, error=str(exc))
