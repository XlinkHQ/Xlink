from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.backup.models import BackupScope


class BackupExportRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    since: datetime | None = None

    @field_validator("since")
    @classmethod
    def validate_since_timezone(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("since must be timezone-aware")
        return v


class BackupRestoreRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    document: dict[str, Any]
    dry_run: bool = False


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
