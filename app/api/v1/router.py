from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routers import (
    agent,
    assignments,
    auth,
    backup,
    failover,
    gitops,
    health,
    monitoring,
    nodes,
    profiles,
    providers,
    scheduler,
    subscriptions,
    traffic,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(nodes.router)
api_router.include_router(profiles.router)
api_router.include_router(providers.router)
api_router.include_router(assignments.router)
api_router.include_router(subscriptions.router)
api_router.include_router(traffic.router)
api_router.include_router(monitoring.router)
api_router.include_router(scheduler.router)
api_router.include_router(failover.router)
api_router.include_router(backup.router)
api_router.include_router(gitops.router)
api_router.include_router(agent.router)
