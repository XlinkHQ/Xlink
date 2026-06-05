from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class BackupScope(StrEnum):
    FULL = "full"
    INCREMENTAL = "incremental"


@dataclass(frozen=True, slots=True)
class BackupDocument:
    schema_version: int
    scope: BackupScope
    exported_at: datetime
    data: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    checksum: str | None = None

    @classmethod
    def create(
        cls,
        *,
        scope: BackupScope,
        data: dict[str, list[dict[str, Any]]],
        checksum: str | None = None,
    ) -> BackupDocument:
        return cls(
            schema_version=1,
            scope=scope,
            exported_at=datetime.now(UTC),
            data=data,
            checksum=checksum,
        )
