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


async def handle_traffic_limit_reached(event: DomainEvent) -> None:
    if not isinstance(event, TrafficLimitReached):
        return
    logger.warning(
        "traffic_limit_reached_disable_assignment",
        assignment_id=str(event.assignment_id),
        user_id=str(event.user_id),
        limit_bytes=event.limit_bytes,
        used_bytes=event.used_bytes,
    )


async def handle_node_offline(event: DomainEvent) -> None:
    if not isinstance(event, NodeOffline):
        return
    logger.critical(
        "node_offline_detected",
        node_id=str(event.node_id),
        reason=event.reason,
    )


def register_default_handlers(registry: EventRegistry) -> None:

    for event_type in (
        AssignmentCreated,
        AssignmentDisabled,
        AssignmentExpired,
        NodeRecovered,
        ProviderUnavailable,
        SubscriptionGenerated,
    ):
        registry.subscribe(event_type, log_domain_event)

    registry.subscribe(TrafficLimitReached, handle_traffic_limit_reached)
    registry.subscribe(NodeOffline, handle_node_offline)
