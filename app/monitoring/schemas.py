from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MetricRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    value: float
    labels: dict[str, str]


class MetricsSnapshotRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    metrics: tuple[MetricRead, ...]
    collected_at: datetime
