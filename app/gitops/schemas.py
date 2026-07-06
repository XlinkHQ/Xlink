from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.domain.gitops import GitOpsAction


class SnapshotPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_type: str
    entity_id: uuid.UUID | None = None
    payload: dict[str, Any]


class CommitRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    before: SnapshotPayload | None = None
    after: SnapshotPayload
    actor: str | None = None
    message: str | None = None


class DiffRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    before: SnapshotPayload
    after: SnapshotPayload


class DiffResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    added: dict[str, Any]
    changed: dict[str, dict[str, Any]]
    removed: dict[str, Any]


class GitOpsRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID | None
    action: GitOpsAction
    actor: str | None = None
    message: str | None = None
    snapshot: dict[str, Any]
    diff: dict[str, Any]
    created_at: datetime
