from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.domain.gitops import GitOpsAction


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
