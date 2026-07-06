from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable

from app.events.models import DomainEvent

type EventHandler = Callable[[DomainEvent], Awaitable[None]]


class EventRegistry:
    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[EventHandler]] = defaultdict(list)

    def subscribe(
        self,
        event_type: type[DomainEvent],
        handler: EventHandler,
        *,
        replace: bool = False,
    ) -> None:
        handlers = self._handlers[event_type]
        if replace:
            self._handlers[event_type] = [handler]
            return
        if handler not in handlers:
            handlers.append(handler)

    def unsubscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        handlers = self._handlers.get(event_type)
        if not handlers:
            return
        self._handlers[event_type] = [
            registered for registered in handlers if registered != handler
        ]

    def handlers_for(self, event: DomainEvent) -> tuple[EventHandler, ...]:
        seen: set[EventHandler] = set()
        handlers: list[EventHandler] = []
        for event_type, registered in self._handlers.items():
            if isinstance(event, event_type):
                for h in registered:
                    if h not in seen:
                        seen.add(h)
                        handlers.append(h)
        return tuple(handlers)

    def count(self, event_type: type[DomainEvent]) -> int:
        return len(self._handlers.get(event_type, ()))
