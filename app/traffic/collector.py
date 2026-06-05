from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.traffic.schemas import TrafficBatch, TrafficSample


@dataclass(frozen=True, slots=True)
class PreparedBatch:
    rows: tuple[dict, ...]
    received: int
    deduped: int
    skipped: int


class TrafficCollector:
    def prepare(self, batch: TrafficBatch) -> PreparedBatch:
        received = len(batch.samples)
        seen: set[tuple[uuid.UUID, object]] = set()
        rows: list[dict] = []
        deduped = 0
        skipped = 0
        for sample in batch.samples:
            if not self._valid(sample):
                skipped += 1
                continue
            key = (sample.assignment_id, sample.collected_at)
            if key in seen:
                deduped += 1
                continue
            seen.add(key)
            rows.append(self._row(batch.node_id, sample))
        return PreparedBatch(
            rows=tuple(rows),
            received=received,
            deduped=deduped,
            skipped=skipped,
        )

    def _valid(self, sample: TrafficSample) -> bool:
        return sample.upload_bytes >= 0 and sample.download_bytes >= 0

    def _row(self, node_id: uuid.UUID, sample: TrafficSample) -> dict:
        return {
            "assignment_id": sample.assignment_id,
            "node_id": node_id,
            "upload_bytes": sample.upload_bytes,
            "download_bytes": sample.download_bytes,
            "total_bytes": sample.total_bytes,
            "collected_at": sample.collected_at,
        }
