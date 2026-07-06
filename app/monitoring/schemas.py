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


class SystemStatsRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    cpu_percent: float
    cpu_cores: int
    ram_used_bytes: int
    ram_total_bytes: int
    disk_used_bytes: int
    disk_total_bytes: int
    uptime_seconds: int
    load_avg_1: float
    load_avg_5: float
    load_avg_15: float
    swap_used_bytes: int
    swap_total_bytes: int
    process_count: int
    hostname: str = ""
    os_name: str = ""
    os_slug: str = ""
    kernel: str = ""
    arch: str = ""
    ip_address: str = ""
    ip6_address: str = ""
    mac_address: str = ""
    python_version: str = ""
    app_version: str = ""
