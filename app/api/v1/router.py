from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routers import (
    admin_roles,
    agent,
    api_keys,
    assignments,
    audit,
    auth,
    backup,
    certificates,
    cli,
    failover,
    gitops,
    groups,
    health,
    inbound_hosts,
    monitoring,
    nodes,
    profiles,
    providers,
    routing,
    scheduler,
    settings,
    subscriptions,
    traffic,
    user_templates,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(admin_roles.router)
api_router.include_router(nodes.router)
api_router.include_router(profiles.router)
api_router.include_router(groups.router)
api_router.include_router(inbound_hosts.router)
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
api_router.include_router(settings.router)
api_router.include_router(audit.router)
api_router.include_router(api_keys.router)
api_router.include_router(cli.router)
api_router.include_router(certificates.router)
api_router.include_router(user_templates.router)
api_router.include_router(routing.router)
