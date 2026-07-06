from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path

import anyio

from app.backup.models import BackupDocument
from app.backup.service import BackupService
from app.core.logging import get_logger
from app.db.session import Database

logger = get_logger("xlink.backup.scheduler")


def _serialize(document: BackupDocument) -> str:
    payload = dataclasses.asdict(document)
    payload["scope"] = document.scope.value
    payload["exported_at"] = document.exported_at.isoformat()
    return json.dumps(payload, default=str, indent=2)


def _write_backup(directory: Path, keep: int, payload: str) -> tuple[Path, int]:
    directory.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        directory.chmod(0o700)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = directory / f"xlink-backup-{stamp}.json"
    # Backups carry node/proxy secrets in cleartext — restrict to owner before
    # writing so they aren't world/group-readable on shared hosts.
    target.touch(mode=0o600, exist_ok=True)
    with contextlib.suppress(OSError):
        target.chmod(0o600)
    target.write_text(payload, encoding="utf-8")

    backups = sorted(directory.glob("xlink-backup-*.json"))
    for stale in backups[: max(0, len(backups) - keep)]:
        with contextlib.suppress(OSError):
            stale.unlink()
    return target, min(len(backups), keep)


async def run_backup(db: Database, *, directory: Path, keep: int) -> Path:
    async with db.session() as session:
        document = await BackupService(session).export_full()

    target, kept = await anyio.to_thread.run_sync(
        _write_backup, directory, keep, _serialize(document)
    )
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
