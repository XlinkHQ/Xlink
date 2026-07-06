from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.domain.client_assignment import AssignmentStatus
from app.providers.base.models import ProviderKind
from app.schemas.base import APIModel, InputModel


class AssignmentCreate(InputModel):
    user_id: uuid.UUID
    profile_id: uuid.UUID

    node_id: uuid.UUID | None = Field(default=None)
    provider_kind: ProviderKind
    expires_at: datetime | None = Field(default=None)
    traffic_limit_bytes: int | None = Field(default=None, ge=0)
    group_id: uuid.UUID | None = Field(default=None)


class AssignmentUpdate(InputModel):
    status: AssignmentStatus | None = Field(default=None)
    expires_at: datetime | None = Field(default=None)
    traffic_limit_bytes: int | None = Field(default=None, ge=0)
    expected_version: int | None = Field(default=None, ge=1)


class AssignmentRead(APIModel):
    id: uuid.UUID
    user_id: uuid.UUID
    profile_id: uuid.UUID
    node_id: uuid.UUID
    provider_kind: ProviderKind
    provider_client_id: str | None
    status: AssignmentStatus
    expires_at: datetime | None
    traffic_limit_bytes: int | None
    used_bytes: int
    version: int
    created_at: datetime
    updated_at: datetime
