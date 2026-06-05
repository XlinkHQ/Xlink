from __future__ import annotations

from app.monitoring.models import MetricsSnapshot


class PrometheusExporter:
    def export(self, snapshot: MetricsSnapshot) -> str:
        lines: list[str] = []
        for metric in sorted(
            snapshot.metrics,
            key=lambda item: (item.name, sorted(item.labels.items())),
        ):
            labels = self._labels(metric.labels)
            lines.append(f"# TYPE xlink_{metric.name} gauge")
            lines.append(f"xlink_{metric.name}{labels} {metric.value:g}")
        return "\n".join(lines) + "\n"

    def _labels(self, labels: dict[str, str]) -> str:
        if not labels:
            return ""
        encoded = ",".join(f'{key}="{value}"' for key, value in sorted(labels.items()))
        return "{" + encoded + "}"
