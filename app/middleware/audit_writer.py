from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass

from app.core.logging import get_logger
from app.db.session import Database

logger = get_logger("xlink.audit")

_MAX_QUEUE = 10000
_BATCH = 200
_FLUSH_INTERVAL = 1.0


@dataclass(frozen=True, slots=True)
class AuditEntry:
    actor_id: object
    actor_username: str
    method: str
    path: str
    action: str
    status_code: int
    ip_address: str


class AuditWriter:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._queue: asyncio.Queue[AuditEntry] = asyncio.Queue(maxsize=_MAX_QUEUE)
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._dropped = 0

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="audit-writer")
        logger.info("audit_writer_started")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        finally:
            self._task = None
        logger.info("audit_writer_stopped", dropped=self._dropped)

    def submit(self, entry: AuditEntry) -> None:
        try:
            self._queue.put_nowait(entry)
        except asyncio.QueueFull:
            self._dropped += 1
            if self._dropped % 100 == 1:
                logger.warning("audit_queue_full", dropped=self._dropped)

    async def _run(self) -> None:
        while not (self._stopping.is_set() and self._queue.empty()):
            batch = await self._collect_batch()
            if batch:
                await self._flush(batch)

    async def _collect_batch(self) -> list[AuditEntry]:
        batch: list[AuditEntry] = []
        try:
            first = await asyncio.wait_for(self._queue.get(), timeout=_FLUSH_INTERVAL)
        except TimeoutError:
            return batch
        batch.append(first)
        while len(batch) < _BATCH:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return batch

    async def _flush(self, batch: list[AuditEntry]) -> None:
        from app.domain.audit_log import AuditLog

        try:
            async with self._db.session() as session:
                session.add_all(
                    AuditLog(
                        actor_id=e.actor_id,
                        actor_username=e.actor_username,
                        method=e.method,
                        path=e.path,
                        action=e.action,
                        status_code=e.status_code,
                        ip_address=e.ip_address,
                    )
                    for e in batch
                )
        except Exception:
            logger.exception("audit_flush_failed", count=len(batch))
