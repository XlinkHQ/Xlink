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
    # Weight effective load by usage_coefficient so a deliberately-throttled node
    # (coeff>1) isn't scored as if it had full headroom — matches how the traffic
    # layer applies the same coefficient.
    coeff = node.usage_coefficient if node.usage_coefficient and node.usage_coefficient > 0 else 1.0
    effective = node.current_users * coeff
    load_ratio = min(1.0, max(0.0, effective / max_users))
    # Normalize capacity PER-NODE (fraction free of its own max), not against a
    # fixed global ceiling — otherwise small nodes flat-line and "capacity first"
    # would prefer a 90%-full big node over a 5%-full small one.
    free_capacity_ratio = max(0.0, 1.0 - load_ratio)
    region = node.node_metadata.get("region")
    region_match = preferred_region is not None and region == preferred_region
    try:
        traffic_load = float(node.node_metadata.get("traffic_load", 0.0) or 0.0)
    except (ValueError, TypeError):
        traffic_load = 0.0
    return ScoreInputs(
        load_ratio=load_ratio,
        free_capacity_ratio=free_capacity_ratio,
        region_match=region_match,
        traffic_load=max(0.0, min(1.0, traffic_load)),
    )
