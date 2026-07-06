from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agent.domain import CommandKind, DriftSeverity, ProviderHealthStatus


class TrafficSampleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: uuid.UUID
    upload_bytes: int = Field(ge=0)
    download_bytes: int = Field(ge=0)
    collected_at: datetime


class TrafficReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(min_length=1, max_length=128)
    samples: list[TrafficSampleIn] = Field(default_factory=list, max_length=10000)


class ConnectionSampleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: uuid.UUID
    source_ip: str = Field(min_length=1, max_length=64)


class ConnectionReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    samples: list[ConnectionSampleIn] = Field(default_factory=list, max_length=10000)


class TrafficReportResponse(BaseModel):
    node_id: uuid.UUID
    batch_id: str
    received: int
    inserted: int
    duplicates: int
    skipped: int


class DesiredConfig(BaseModel):
    node_id: uuid.UUID
    config_version: str
    config: dict[str, Any]
    assignment_count: int


class ReportedStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_version: str | None = None
    agent_version: str | None = None
    applied: dict[str, Any] = Field(default_factory=dict)
    provider_status: dict[str, str] = Field(default_factory=dict)


class DriftReportOut(BaseModel):
    node_id: uuid.UUID
    severity: DriftSeverity
    desired_version: str
    reported_version: str | None
    drift: dict[str, Any]
    remediated: bool


class CommandOut(BaseModel):
    command_id: uuid.UUID
    node_id: uuid.UUID
    kind: CommandKind
    payload: dict[str, Any]
    signature: str
    origin: str
    attempts: int
    max_attempts: int


class CommandLeaseResponse(BaseModel):
    lease_token: str | None
    commands: list[CommandOut] = Field(default_factory=list)


class CommandResultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: uuid.UUID
    lease_token: str
    success: bool
    result: dict[str, Any] = Field(default_factory=dict)


class EnqueueCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: CommandKind
    payload: dict[str, Any] = Field(default_factory=dict)
    origin: str = "operator"
    max_attempts: int = Field(default=3, ge=1, le=10)


class ProviderHealthIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_name: str = Field(min_length=1, max_length=64)
    status: ProviderHealthStatus
    latency_ms: float | None = Field(default=None, ge=0)
    detail: str | None = Field(default=None, max_length=1024)


class ProviderHealthReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checks: list[ProviderHealthIn] = Field(default_factory=list, max_length=64)


class MetricSampleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    value: float
    observed_at: datetime


class MetricsStreamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    samples: list[MetricSampleIn] = Field(default_factory=list, max_length=1000)


class LogLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = Field(min_length=1, max_length=16)
    message: str = Field(min_length=1, max_length=8192)
    observed_at: datetime
    source: str | None = Field(default=None, max_length=16)


class LogStreamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[LogLineIn] = Field(default_factory=list, max_length=1000)


class CommandResultResponse(BaseModel):
    command_id: uuid.UUID
    status: str


class StreamAck(BaseModel):
    accepted: int
    dropped: int
