from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.backup.models import BackupScope


class BackupRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int
    scope: BackupScope
    exported_at: datetime
    data: dict[str, list[dict[str, Any]]]
    checksum: str | None = None


class RestoreResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    dry_run: bool
    users: int = 0
    nodes: int = 0
    profiles: int = 0
    assignments: int = 0
