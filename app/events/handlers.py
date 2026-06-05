from __future__ import annotations

from app.core.logging import get_logger
from app.events.models import (
    AssignmentCreated,
    AssignmentDisabled,
    AssignmentExpired,
    DomainEvent,
    NodeOffline,
    NodeRecovered,
    ProviderUnavailable,
    SubscriptionGenerated,
    TrafficLimitReached,
)
from app.events.registry import EventRegistry

logger = get_logger("xlink.events.handlers")


async def log_domain_event(event: DomainEvent) -> None:
    logger.info(
        "domain_event_observed",
        event_name=event.event_name,
        event_id=str(event.event_id),
        correlation_id=event.correlation_id,
    )


def register_default_handlers(registry: EventRegistry) -> None:
    for event_type in (
        AssignmentCreated,
        AssignmentDisabled,
        AssignmentExpired,
        NodeOffline,
        NodeRecovered,
        ProviderUnavailable,
        TrafficLimitReached,
        SubscriptionGenerated,
    ):
        registry.subscribe(event_type, log_domain_event)
