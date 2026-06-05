from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.05
    max_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0

    def delay_for(self, attempt: int) -> float:
        delay = self.base_delay_seconds * (self.backoff_multiplier ** max(0, attempt - 1))
        return min(delay, self.max_delay_seconds)


@dataclass(frozen=True, slots=True)
class CircuitBreakerConfig:
    enabled: bool = False
    failure_threshold: int = 5
    reset_timeout_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class XrayGatewayConfig:
    endpoint: str = "inmemory://xray"
    timeout_seconds: float = 5.0
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
