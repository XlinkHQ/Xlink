from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.leader import LeaderElector
from app.core.logging import get_logger
from app.db.redis import RedisCache
from app.db.session import Database
from app.domain.user import User, UserRole
from app.webhooks import events
from app.webhooks.dispatcher import WebhookDispatcher

logger = get_logger("xlink.notifications")


_DEDUP_TTL_SECONDS = 7 * 24 * 3600


def _human_gb(num_bytes: int) -> str:
    return f"{num_bytes / (1024**3):.1f}GB"


class NotificationJob:
    def __init__(
        self,
        db: Database,
        dispatcher: WebhookDispatcher,
        cache: RedisCache,
        *,
        interval_seconds: int,
        expiring_days: int,
        usage_percent: int,
        leader: LeaderElector | None = None,
    ) -> None:
        self._db = db
        self._dispatcher = dispatcher
        self._cache = cache
        self._interval = interval_seconds
        self._expiring_days = expiring_days
        self._usage_percent = usage_percent
        self._leader = leader
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="notifications")
        logger.info("notifications_started", interval_seconds=self._interval)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
        logger.info("notifications_stopped")

    async def _run(self) -> None:
        while not self._stopping.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            if self._stopping.is_set():
                break
            if self._leader is not None and not self._leader.is_leader:
                continue
            try:
                await self.scan_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("notifications_scan_failed")

    async def _already_notified(self, key: str) -> bool:
        try:
            was_set = await self._cache.client.set(key, b"1", nx=True, ex=_DEDUP_TTL_SECONDS)
        except Exception as exc:
            # Redis outage: fail closed (suppress) to avoid a duplicate-storm on
            # every scan cycle, but log loudly so silent sent=0 scans are visible.
            logger.warning("notifications_dedup_redis_error", key=key, error=str(exc))
            return True
        return not was_set

    async def _load_settings(self, session) -> bool:
        from app.domain.app_settings import AppSettings

        row = await session.get(AppSettings, 1)
        if row is None:
            return True
        if not row.notify_enabled:
            return False
        self._expiring_days = row.notify_expiring_days
        self._usage_percent = row.notify_usage_percent
        self._dispatcher.apply_overrides(
            webhook_address=row.webhook_address,
            discord_webhook_url=row.discord_webhook_url,
            telegram_bot_token=row.telegram_bot_token,
            telegram_chat_ids=row.telegram_chat_ids,
        )
        return True

    async def scan_once(self) -> int:
        now = datetime.now(UTC)
        sent = 0
        async with self._db.session() as session:
            if not await self._load_settings(session):
                return 0
            # Use the maintained account total (users_data_usage) — the SAME number
            # enforcement and the UI use — NOT a sum over ACTIVE assignments: a user
            # who crossed their limit flips to LIMITED, so an ACTIVE-only sum reads
            # low and the "N% used" warning would fire late or never.
            stmt = select(User, User.users_data_usage).where(
                User.role == UserRole.USER,
                User.is_active.is_(True),
                User.removed.is_(False),
            )
            rows = (await session.execute(stmt)).all()

        for user, used in rows:
            sent += await self._maybe_warn(user, int(used or 0), now)
        if sent:
            logger.info("notifications_dispatched", count=sent)
        return sent

    async def _maybe_warn(self, user: User, used: int, now: datetime) -> int:
        sent = 0

        if user.expire_at is not None:
            exp = user.expire_at if user.expire_at.tzinfo else user.expire_at.replace(tzinfo=UTC)
            days_left = (exp - now).days
            if 0 <= days_left <= self._expiring_days:
                key = f"notify:expiring:{user.id}:{exp.date().isoformat()}"
                if not await self._already_notified(key):
                    await self._dispatcher.dispatch(
                        events.USER_EXPIRING_SOON,
                        user.username,
                        detail=f"Expires in {days_left} day(s) — {exp.date().isoformat()}",
                    )
                    sent += 1

        limit = user.data_limit_bytes
        if limit and limit > 0:
            pct = int(used * 100 / limit)
            if pct >= self._usage_percent:
                bucket = min(100, (pct // 10) * 10)
                key = f"notify:datawarn:{user.id}:{limit}:{bucket}"
                if not await self._already_notified(key):
                    await self._dispatcher.dispatch(
                        events.USER_DATA_WARNING,
                        user.username,
                        detail=f"Used {pct}% — {_human_gb(used)} of {_human_gb(limit)}",
                    )
                    sent += 1
        return sent
