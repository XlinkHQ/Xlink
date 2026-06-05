from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI

from app.agent.commands import CommandSigner
from app.agent.reconcile import AgentReconcileJob
from app.core.config import Settings, get_settings
from app.core.jobs import TokenCleanupJob
from app.core.logging import configure_logging, get_logger
from app.db.redis import RedisCache
from app.db.session import Database
from app.events.bus import EventBus
from app.events.handlers import register_default_handlers
from app.events.registry import EventRegistry
from app.monitoring.summary import MetricsRefreshJob
from app.providers.base.registry import ProviderRegistry
from app.providers.discovery import build_registry
from app.traffic.scheduler import TrafficRetentionJob

logger = get_logger("xlink.lifespan")


@dataclass(slots=True)
class AppState:
    settings: Settings
    db: Database
    cache: RedisCache
    providers: ProviderRegistry
    events: EventBus
    cleanup_job: TokenCleanupJob | None = None
    metrics_job: MetricsRefreshJob | None = None
    traffic_retention_job: TrafficRetentionJob | None = None
    agent_reconcile_job: AgentReconcileJob | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)

    logger.info("startup_begin", env=settings.env, project=settings.project_name)
    db = Database(settings)
    cache = RedisCache(settings)

    providers = build_registry()
    logger.info("providers_discovered", providers=providers.names())
    event_registry = EventRegistry()
    register_default_handlers(event_registry)
    events = EventBus(event_registry)

    cleanup_job: TokenCleanupJob | None = None
    if settings.token_cleanup_enabled:
        cleanup_job = TokenCleanupJob(db, interval_seconds=settings.token_cleanup_interval_seconds)
        cleanup_job.start()

    metrics_job: MetricsRefreshJob | None = None
    if settings.metrics_summary_enabled:
        metrics_job = MetricsRefreshJob(
            db,
            cache,
            providers,
            interval_seconds=settings.metrics_summary_refresh_seconds,
            ttl_seconds=settings.metrics_summary_ttl_seconds,
        )
        metrics_job.start()

    traffic_retention_job: TrafficRetentionJob | None = None
    if settings.traffic_retention_enabled:
        traffic_retention_job = TrafficRetentionJob(
            db,
            interval_seconds=settings.traffic_retention_interval_seconds,
            retention_days=settings.traffic_retention_days,
        )
        traffic_retention_job.start()

    agent_reconcile_job: AgentReconcileJob | None = None
    if settings.agent_reconcile_enabled:
        agent_reconcile_job = AgentReconcileJob(
            db,
            signer=CommandSigner(settings.agent_signing_secret),
            events=events,
            interval_seconds=settings.agent_reconcile_interval_seconds,
            self_healing_enabled=settings.agent_self_healing_enabled,
            target_version=settings.agent_target_version,
        )
        agent_reconcile_job.start()

    app.state.xlink = AppState(
        settings=settings,
        db=db,
        cache=cache,
        providers=providers,
        events=events,
        cleanup_job=cleanup_job,
        metrics_job=metrics_job,
        traffic_retention_job=traffic_retention_job,
        agent_reconcile_job=agent_reconcile_job,
    )
    logger.info("startup_complete")

    try:
        yield
    finally:
        logger.info("shutdown_begin")
        if cleanup_job is not None:
            await cleanup_job.stop()
        if metrics_job is not None:
            await metrics_job.stop()
        if traffic_retention_job is not None:
            await traffic_retention_job.stop()
        if agent_reconcile_job is not None:
            await agent_reconcile_job.stop()
        await cache.close()
        await db.dispose()
        logger.info("shutdown_complete")
