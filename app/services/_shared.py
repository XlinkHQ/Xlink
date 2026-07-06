from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from sqlalchemy.orm.exc import StaleDataError

from app.core.exceptions import ConflictError

if TYPE_CHECKING:
    from app.subscription.service import SubscriptionService

async def invalidate_subscription_cache(
    subscription_service: SubscriptionService | None,
    node_id: uuid.UUID | None = None,
) -> None:
    if subscription_service is not None:
        await subscription_service.invalidate_cache()
        if node_id is not None:
            await subscription_service.notify_node_changed(node_id)


async def save_or_conflict[T](
    save: Callable[[T], Awaitable[T]], entity: T, label: str
) -> T:
    try:
        return await save(entity)
    except StaleDataError as exc:
        raise ConflictError(
            f"{label} was modified concurrently.", code="version_conflict"
        ) from exc
