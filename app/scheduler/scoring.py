from __future__ import annotations

from dataclasses import dataclass

from app.domain.node import Node


@dataclass(frozen=True, slots=True)
class ScoreInputs:
    load_ratio: float
    free_capacity_ratio: float
    region_match: bool
    traffic_load: float


def score_inputs(node: Node, preferred_region: str | None = None) -> ScoreInputs:
    max_users = max(1, node.max_users)
    load_ratio = min(1.0, max(0.0, node.current_users / max_users))
    free_capacity_ratio = max(0.0, 1.0 - load_ratio)
    region = node.node_metadata.get("region")
    region_match = preferred_region is not None and region == preferred_region
    traffic_load = float(node.node_metadata.get("traffic_load", 0.0) or 0.0)
    return ScoreInputs(
        load_ratio=load_ratio,
        free_capacity_ratio=free_capacity_ratio,
        region_match=region_match,
        traffic_load=max(0.0, min(1.0, traffic_load)),
    )
