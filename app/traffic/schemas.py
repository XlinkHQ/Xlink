from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrafficSample(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    assignment_id: uuid.UUID
    upload_bytes: int = Field(ge=0)
    download_bytes: int = Field(ge=0)
    collected_at: datetime

    @property
    def total_bytes(self) -> int:
        return self.upload_bytes + self.download_bytes


class TrafficBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: uuid.UUID
    batch_id: str = Field(min_length=1, max_length=128)
    samples: tuple[TrafficSample, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _bound_samples(self) -> TrafficBatch:
        if len(self.samples) > 10000:
            raise ValueError("traffic batch exceeds 10000 samples")
        return self


class TrafficIngestResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: uuid.UUID
    batch_id: str
    received: int
    inserted: int
    duplicates: int
    skipped: int


class TrafficUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    assignment_id: uuid.UUID
    upload_bytes: int
    download_bytes: int
    total_bytes: int
    sample_count: int


class TrafficTotals(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_bytes: int
    upload_bytes: int
    download_bytes: int
    record_count: int
