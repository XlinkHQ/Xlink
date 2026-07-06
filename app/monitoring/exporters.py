from __future__ import annotations

import math

from app.monitoring.models import MetricsSnapshot


class PrometheusExporter:
    def export(self, snapshot: MetricsSnapshot) -> str:
        lines: list[str] = []
        seen_types: set[str] = set()
        for metric in sorted(
            snapshot.metrics,
            key=lambda item: (item.name, sorted(item.labels.items())),
        ):
            labels = self._labels(metric.labels)
            if metric.name not in seen_types:
                lines.append(f"# TYPE xlink_{metric.name} gauge")
                seen_types.add(metric.name)
            lines.append(f"xlink_{metric.name}{labels} {self._format(metric.value)}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _format(value: float) -> str:
        v = float(value)
        if math.isnan(v):
            return "NaN"
        if math.isinf(v):
            return "+Inf" if v > 0 else "-Inf"
        return str(int(v)) if v.is_integer() else repr(v)

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    def _labels(self, labels: dict[str, str]) -> str:
        if not labels:
            return ""
        encoded = ",".join(
            f'{key}="{self._escape(value)}"' for key, value in sorted(labels.items())
        )
        return "{" + encoded + "}"
