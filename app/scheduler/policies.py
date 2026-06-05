from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.node import Node
from app.scheduler.models import NodeScore, SchedulerPolicyName
from app.scheduler.scoring import score_inputs


class SchedulerPolicy(ABC):
    name: SchedulerPolicyName

    @abstractmethod
    def score(self, node: Node, *, preferred_region: str | None = None) -> NodeScore: ...


class WeightedPolicy(SchedulerPolicy):
    name = SchedulerPolicyName.CUSTOM_WEIGHTED

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._weights = weights or {
            "load": 0.35,
            "capacity": 0.35,
            "region": 0.2,
            "traffic": 0.1,
        }

    def score(self, node: Node, *, preferred_region: str | None = None) -> NodeScore:
        values = score_inputs(node, preferred_region)
        score = (
            self._weights.get("load", 0.0) * (1.0 - values.load_ratio)
            + self._weights.get("capacity", 0.0) * values.free_capacity_ratio
            + self._weights.get("region", 0.0) * (1.0 if values.region_match else 0.0)
            + self._weights.get("traffic", 0.0) * (1.0 - values.traffic_load)
        )
        reasons = (
            f"load={values.load_ratio:.3f}",
            f"capacity={values.free_capacity_ratio:.3f}",
            f"region_match={values.region_match}",
            f"traffic={values.traffic_load:.3f}",
        )
        return NodeScore(node_id=node.id, score=round(score, 6), reasons=reasons)


class LeastLoadedPolicy(WeightedPolicy):
    name = SchedulerPolicyName.LEAST_LOADED

    def __init__(self) -> None:
        super().__init__({"load": 1.0})


class CapacityFirstPolicy(WeightedPolicy):
    name = SchedulerPolicyName.CAPACITY_FIRST

    def __init__(self) -> None:
        super().__init__({"capacity": 1.0})


class RegionFirstPolicy(WeightedPolicy):
    name = SchedulerPolicyName.REGION_FIRST

    def __init__(self) -> None:
        super().__init__({"region": 0.7, "load": 0.2, "capacity": 0.1})


class BalancedPolicy(WeightedPolicy):
    name = SchedulerPolicyName.BALANCED


def policy_for(
    name: SchedulerPolicyName, weights: dict[str, float] | None = None
) -> SchedulerPolicy:
    if name is SchedulerPolicyName.LEAST_LOADED:
        return LeastLoadedPolicy()
    if name is SchedulerPolicyName.CAPACITY_FIRST:
        return CapacityFirstPolicy()
    if name is SchedulerPolicyName.REGION_FIRST:
        return RegionFirstPolicy()
    if name is SchedulerPolicyName.CUSTOM_WEIGHTED:
        return WeightedPolicy(weights)
    return BalancedPolicy()
