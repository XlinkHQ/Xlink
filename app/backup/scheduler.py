from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from pathlib import Path

import anyio

from app.backup.models import BackupScope
from app.backup.stream_writer import prune_backups, stream_export_to_file
from app.core.logging import get_logger
from app.db.session import Database

logger = get_logger("xlink.backup.scheduler")


def _prepare_dir(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        directory.chmod(0o700)


async def run_backup(db: Database, *, directory: Path, keep: int) -> Path:
    await anyio.to_thread.run_sync(_prepare_dir, directory)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = directory / f"xlink-backup-{stamp}.json"
    # Write to a sibling tmp file then atomically rename: readers/retention never
    # observe a partially-written backup, and the export streams row-by-row so
    # memory stays bounded regardless of dataset size (500k+ assignment rows).
    tmp = directory / f".xlink-backup-{stamp}.json.tmp"

    await stream_export_to_file(db, target=target, tmp=tmp, scope=BackupScope.FULL)
    kept = await anyio.to_thread.run_sync(prune_backups, directory, keep)

    logger.info("auto_backup_written", path=str(target), kept=kept)
    return target


class BackupJob:
    def __init__(
        self,
        db: Database,
        *,
        interval_seconds: int,
        directory: str,
        keep: int,
        leader=None,
    ) -> None:
        self._db = db
        self._interval = interval_seconds
        self._dir = Path(directory)
        self._keep = keep
        self._leader = leader
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="auto-backup")
        logger.info(
            "auto_backup_started",
            interval_seconds=self._interval,
            directory=str(self._dir),
            keep=self._keep,
        )

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
        logger.info("auto_backup_stopped")

    async def _run(self) -> None:
        while not self._stopping.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            if self._stopping.is_set():
                break
            if self._leader is not None and not self._leader.is_leader:
                continue
            try:
                await run_backup(self._db, directory=self._dir, keep=self._keep)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("auto_backup_failed")
