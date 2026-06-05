from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Final

from app.core.logging import get_logger
from app.events.models import DomainEvent
from app.events.registry import EventHandler, EventRegistry

logger = get_logger("xlink.events")
_NO_DELAY: Final[float] = 0.0


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.05
    max_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0

    def delay_for(self, attempt: int) -> float:
        if self.base_delay_seconds <= _NO_DELAY:
            return _NO_DELAY
        delay = self.base_delay_seconds * (self.backoff_multiplier ** max(0, attempt - 1))
        return min(delay, self.max_delay_seconds)


@dataclass(frozen=True, slots=True)
class EventBusConfig:
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    concurrent_handlers: bool = True
    fire_and_forget: bool = False


@dataclass(frozen=True, slots=True)
class HandlerResult:
    event_name: str
    handler_name: str
    attempts: int
    succeeded: bool
    error: str | None = None


class EventBus:
    def __init__(
        self,
        registry: EventRegistry | None = None,
        config: EventBusConfig | None = None,
    ) -> None:
        self._registry = registry or EventRegistry()
        self._config = config or EventBusConfig()
        self._background: set[asyncio.Task] = set()

    @property
    def registry(self) -> EventRegistry:
        return self._registry

    def publish_background(self, event: DomainEvent) -> None:
        task = asyncio.create_task(self._publish_safe(event))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _publish_safe(self, event: DomainEvent) -> None:
        try:
            await self._publish_now(event)
        except Exception:
            logger.exception("event_background_publish_failed", event_name=event.event_name)

    async def drain(self) -> None:
        if self._background:
            await asyncio.gather(*list(self._background), return_exceptions=True)

    def subscribe(
        self,
        event_type: type[DomainEvent],
        handler: EventHandler,
        *,
        replace: bool = False,
    ) -> None:
        self._registry.subscribe(event_type, handler, replace=replace)

    async def publish(self, event: DomainEvent) -> tuple[HandlerResult, ...]:
        if self._config.fire_and_forget:
            self.publish_background(event)
            return ()
        return await self._publish_now(event)

    async def _publish_now(self, event: DomainEvent) -> tuple[HandlerResult, ...]:
        handlers = self._registry.handlers_for(event)
        logger.info(
            "event_publish_started",
            event_name=event.event_name,
            event_id=str(event.event_id),
            handler_count=len(handlers),
            correlation_id=event.correlation_id,
        )
        if not handlers:
            logger.info(
                "event_publish_completed",
                event_name=event.event_name,
                event_id=str(event.event_id),
                handler_count=0,
            )
            return ()

        if self._config.concurrent_handlers:
            results = await asyncio.gather(
                *(self._run_handler(handler, event) for handler in handlers)
            )
        else:
            results = []
            for handler in handlers:
                results.append(await self._run_handler(handler, event))

        failed = sum(1 for result in results if not result.succeeded)
        logger.info(
            "event_publish_completed",
            event_name=event.event_name,
            event_id=str(event.event_id),
            handler_count=len(handlers),
            failed_handlers=failed,
        )
        return tuple(results)

    async def _run_handler(self, handler: EventHandler, event: DomainEvent) -> HandlerResult:
        handler_name = _handler_name(handler)
        last_error: Exception | None = None
        attempts = max(1, self._config.retry.max_attempts)
        for attempt in range(1, attempts + 1):
            try:
                await handler(event)
                logger.info(
                    "event_handler_succeeded",
                    event_name=event.event_name,
                    event_id=str(event.event_id),
                    handler=handler_name,
                    attempt=attempt,
                )
                return HandlerResult(
                    event_name=event.event_name,
                    handler_name=handler_name,
                    attempts=attempt,
                    succeeded=True,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "event_handler_failed",
                    event_name=event.event_name,
                    event_id=str(event.event_id),
                    handler=handler_name,
                    attempt=attempt,
                    max_attempts=attempts,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                if attempt < attempts:
                    await asyncio.sleep(self._config.retry.delay_for(attempt))

        return HandlerResult(
            event_name=event.event_name,
            handler_name=handler_name,
            attempts=attempts,
            succeeded=False,
            error=str(last_error) if last_error is not None else None,
        )


def _handler_name(handler: EventHandler) -> str:
    return getattr(handler, "__qualname__", getattr(handler, "__name__", repr(handler)))
