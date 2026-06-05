from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from app.core.logging import get_logger
from app.db.session import Database
from app.repositories.refresh_token import RefreshTokenRepository

logger = get_logger("xlink.jobs")


async def purge_expired_tokens(db: Database) -> int:
    async with db.session() as session:
        repo = RefreshTokenRepository(session)
        deleted = await repo.delete_expired(datetime.now(UTC))
    if deleted:
        logger.info("expired_tokens_purged", deleted=deleted)
    return deleted


class TokenCleanupJob:
    def __init__(self, db: Database, *, interval_seconds: int) -> None:
        self._db = db
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="token-cleanup")
        logger.info("token_cleanup_started", interval_seconds=self._interval)

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
        logger.info("token_cleanup_stopped")

    async def _run(self) -> None:
        while not self._stopping.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            if self._stopping.is_set():
                break
            try:
                await purge_expired_tokens(self._db)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("token_cleanup_failed")
