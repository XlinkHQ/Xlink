from __future__ import annotations

import time
import uuid

from app.core.exceptions import RateLimitError
from app.core.logging import get_logger
from app.db.redis import RedisCache

logger = get_logger("xlink.agent.ingest")

_WINDOW_SECONDS = 60


def _window_key(node_id: uuid.UUID, now: float) -> str:
    return f"agent:ingest:{node_id}:{int(now // _WINDOW_SECONDS)}"


async def enforce_ingest_quota(cache: RedisCache, node_id: uuid.UUID, *, limit: int) -> None:
    """Bound per-node ingest rate. Raises RateLimitError (429) past the limit.

    Fails OPEN on a Redis outage: a limiter blip must not take real nodes
    offline (only bound a flood when the counter is actually reachable). The
    per-IP route limiter in the ASGI middleware is unchanged and independent.
    """
    if limit <= 0:
        return
    now = time.time()
    key = _window_key(node_id, now)
    try:
        async with cache.client.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, _WINDOW_SECONDS, nx=True)
            results = await pipe.execute()
        count = int(results[0])
    except Exception:
        logger.warning("agent_ingest_limit_redis_unavailable", node_id=str(node_id))
        return
    if count > limit:
        logger.warning("agent_ingest_rate_limited", node_id=str(node_id), count=count, limit=limit)
        raise RateLimitError("Node ingest rate limit exceeded.", code="agent_ingest_rate_limited")
