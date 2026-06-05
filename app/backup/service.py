from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.backup.exporter import BackupExporter
from app.backup.importer import BackupImporter
from app.backup.models import BackupDocument, BackupScope
from app.backup.schemas import RestoreResult


class BackupService:
    def __init__(self, session: AsyncSession) -> None:
        self._exporter = BackupExporter(session)
        self._importer = BackupImporter(session)

    async def export_full(self) -> BackupDocument:
        return await self._exporter.export(scope=BackupScope.FULL)

    async def export_incremental(self, *, since: datetime) -> BackupDocument:
        return await self._exporter.export(scope=BackupScope.INCREMENTAL, since=since)

    async def restore(self, document: dict[str, Any], *, dry_run: bool = False) -> RestoreResult:
        return await self._importer.restore(document, dry_run=dry_run)
