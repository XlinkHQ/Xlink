from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.dependencies.core import CacheDep, SessionDep
from app.schemas.health import DependencyHealth, LivenessResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    return LivenessResponse()


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(
    session: SessionDep,
    cache: CacheDep,
    response: Response,
) -> ReadinessResponse:
    db_ok = await _check_db(session)
    redis_ok = await _check_redis(cache)
    ready = db_ok and redis_ok
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if ready else "degraded",
        dependencies=DependencyHealth(database=db_ok, redis=redis_ok),
    )


async def _check_db(session: SessionDep) -> bool:
    from sqlalchemy import text

    try:
        await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _check_redis(cache: CacheDep) -> bool:
    try:
        return await cache.ping()
    except Exception:
        return False
