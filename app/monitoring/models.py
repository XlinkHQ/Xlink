from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class Metric:
    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    metrics: tuple[Metric, ...]
    collected_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def get(self, name: str, **labels: str) -> float:
        for metric in self.metrics:
            if metric.name == name and all(metric.labels.get(k) == v for k, v in labels.items()):
                return metric.value
        return 0.0
