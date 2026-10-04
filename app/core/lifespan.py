from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import IntegrityError

from app.agent.commands import CommandSigner
from app.agent.reconcile import AgentReconcileJob
from app.agent.scheduler import NodeAgentScheduler
from app.backup.scheduler import BackupJob
from app.core.app_state import AppState
from app.core.config import get_settings
from app.core.jobs import AssignmentExpirationJob, TokenCleanupJob
from app.core.logging import configure_logging, get_logger
from app.db.redis import RedisCache
from app.db.session import Database
from app.events.bus import EventBus
from app.events.handlers import register_default_handlers
from app.events.models import (
    AssignmentCreated,
    AssignmentDisabled,
    DomainEvent,
    NodeOffline,
)
from app.events.registry import EventRegistry
from app.failover.auto import AutoFailoverHandler
from app.failover.service import FailoverService
from app.gitops.service import GitOpsService
from app.middleware.audit_writer import AuditWriter
from app.monitoring.summary import MetricsRefreshJob
from app.notifications.job import NotificationJob
from app.observability.collector import DomainMetricsCollector
from app.providers.discovery import build_registry
from app.services.cert_renewal import CertRenewalJob
from app.traffic.scheduler import TrafficRetentionJob, TrafficRollupJob
from app.webhooks.dispatcher import WebhookDispatcher

__all__ = ["AppState", "lifespan"]

logger = get_logger("xlink.lifespan")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)

    logger.info("startup_begin", env=settings.env, project=settings.project_name)
    db = Database(settings)
    cache = RedisCache(settings)

    providers = build_registry(settings.provider_plugins_dir or None)
    logger.info("providers_discovered", providers=providers.names())
    event_registry = EventRegistry()
    register_default_handlers(event_registry)
    events = EventBus(event_registry)

    async def _gitops_snapshot_handler(event: DomainEvent) -> None:
        async with db.session() as session:
            gitops = GitOpsService(session)
            await gitops.snapshot_event(event)

    for _evt_type in (AssignmentCreated, AssignmentDisabled, NodeOffline):
        event_registry.subscribe(_evt_type, _gitops_snapshot_handler)

    if settings.auto_failover_enabled:
        auto_failover = AutoFailoverHandler(
            FailoverService(db, providers, events, cache=cache),
            cooldown_seconds=settings.auto_failover_cooldown_seconds,
        )
        event_registry.subscribe(NodeOffline, auto_failover)

    from app.core.leader import LeaderElector

    # Background jobs run only on a process whose role owns them. `all` (the
    # default) keeps the historical single-process behaviour; `api` serves HTTP
    # and gRPC only; `worker` runs the jobs and no listener.
    role = settings.instance_role
    run_jobs = role.runs_jobs
    logger.info("instance_role", role=role.value, runs_jobs=run_jobs, serves_http=role.serves_http)

    leader = LeaderElector(cache) if run_jobs else None
    if leader is not None:
        leader.start()

    cleanup_job: TokenCleanupJob | None = None
    if run_jobs and settings.token_cleanup_enabled:
        cleanup_job = TokenCleanupJob(
            db, interval_seconds=settings.token_cleanup_interval_seconds, leader=leader
        )
        cleanup_job.start()

    metrics_job: MetricsRefreshJob | None = None
    if run_jobs and settings.metrics_summary_enabled:
        metrics_job = MetricsRefreshJob(
            db,
            cache,
            providers,
            interval_seconds=settings.metrics_summary_refresh_seconds,
            ttl_seconds=settings.metrics_summary_ttl_seconds,
            leader=leader,
        )
        metrics_job.start()

    domain_metrics_collector: DomainMetricsCollector | None = None
    prometheus = getattr(app.state, "prometheus", None)
    if run_jobs and settings.metrics_token is not None and prometheus is not None:
        domain_metrics_collector = DomainMetricsCollector(
            db,
            prometheus,
            interval_seconds=settings.metrics_summary_refresh_seconds,
            leader=leader,
        )
        domain_metrics_collector.start()

    traffic_retention_job: TrafficRetentionJob | None = None
    if run_jobs and settings.traffic_retention_enabled:
        traffic_retention_job = TrafficRetentionJob(
            db,
            interval_seconds=settings.traffic_retention_interval_seconds,
            retention_days=settings.traffic_retention_days,
            raw_retention_days=settings.traffic_raw_retention_days,
            leader=leader,
        )
        traffic_retention_job.start()

    traffic_rollup_job: TrafficRollupJob | None = None
    if run_jobs and settings.traffic_rollup_enabled:
        traffic_rollup_job = TrafficRollupJob(
            db,
            interval_seconds=settings.traffic_rollup_interval_seconds,
            leader=leader,
        )
        traffic_rollup_job.start()

    dispatcher = WebhookDispatcher(settings)

    # Durable delivery: any role may ENQUEUE (an API request that disables a user
    # notifies), but only job-running roles CONSUME. Consumer groups give each
    # message to exactly one worker, so several workers are safe.
    from app.core.queue import DurableQueue

    queue: DurableQueue | None = None
    if settings.durable_queue_enabled:
        queue = DurableQueue(cache.client)
        dispatcher.attach_queue(queue)
        if run_jobs:
            queue.start()

    agent_reconcile_job: AgentReconcileJob | None = None
    if run_jobs and settings.agent_reconcile_enabled:
        agent_reconcile_job = AgentReconcileJob(
            db,
            signer=CommandSigner(settings.agent_signing_secret),
            events=events,
            interval_seconds=settings.agent_reconcile_interval_seconds,
            self_healing_enabled=settings.agent_self_healing_enabled,
            target_version=settings.agent_target_version,
            cache=cache,
            dispatcher=dispatcher,
            leader=leader,
        )
        agent_reconcile_job.start()

    assignment_expiration_job: AssignmentExpirationJob | None = None
    if run_jobs and settings.assignment_expiration_enabled:
        assignment_expiration_job = AssignmentExpirationJob(
            db,
            events,
            interval_seconds=settings.assignment_expiration_interval_seconds,
            cache=cache,
            leader=leader,
        )
        assignment_expiration_job.start()

    notification_job: NotificationJob | None = None
    if run_jobs:
        notification_job = NotificationJob(
            db,
            dispatcher,
            cache,
            interval_seconds=settings.notification_interval_seconds,
            expiring_days=settings.notify_expiring_days,
            usage_percent=settings.notify_usage_percent,
            leader=leader,
        )
        notification_job.start()

    node_agent_scheduler: NodeAgentScheduler | None = None
    if run_jobs and settings.agent_reconcile_enabled:
        node_agent_scheduler = NodeAgentScheduler(
            db,
            events=events,
            dispatcher=dispatcher,
            interval_seconds=settings.node_status_interval_seconds,
            offline_after_seconds=settings.node_offline_after_seconds,
            leader=leader,
        )
        node_agent_scheduler.start()

    backup_job: BackupJob | None = None
    if run_jobs and settings.auto_backup_enabled:
        backup_job = BackupJob(
            db,
            interval_seconds=settings.auto_backup_interval_seconds,
            directory=settings.auto_backup_dir,
            keep=settings.auto_backup_keep,
            leader=leader,
        )
        backup_job.start()

    cert_renewal_job: CertRenewalJob | None = None
    if run_jobs and settings.acme_email:
        cert_renewal_job = CertRenewalJob(
            db,
            cache,
            email=settings.acme_email,
            interval_seconds=settings.acme_renew_interval_seconds,
            window_days=settings.acme_renew_window_days,
            staging=settings.acme_staging,
            leader=leader,
        )
        cert_renewal_job.start()

    # The audit outbox is filled by request handlers, so it is drained by the
    # role that serves them.
    audit_writer: AuditWriter | None = None
    if role.serves_http:
        audit_writer = AuditWriter(db)
        audit_writer.start()

    # gRPC binds a port, so only the HTTP-serving role may start it — two
    # processes would otherwise fight over it.
    grpc_server = None
    if role.serves_http:
        from app.agent.grpc.server import GrpcServer

        grpc_server = GrpcServer(db, cache, events, settings)
        try:
            await grpc_server.start()
        except Exception:
            logger.exception("grpc_start_failed")

    if settings.admin_username and settings.admin_password:
        try:
            async with db.session() as session:
                from app.core.security import hash_password_async
                from app.domain.user import User, UserRole
                from app.repositories.user import UserRepository

                repo = UserRepository(session)
                existing = await repo.get_by_username(settings.admin_username)
                if existing is None:
                    pw = settings.admin_password.get_secret_value()
                    if settings.is_production:
                        from app.core.security import validate_password_strength

                        try:
                            validate_password_strength(pw)
                        except ValueError as exc:
                            logger.error("admin_bootstrap_weak_password", error=str(exc))
                            raise
                    hashed = await hash_password_async(pw)
                    admin = User(
                        username=settings.admin_username,
                        hashed_password=hashed,
                        role=UserRole.ADMIN,
                        is_active=True,
                        is_verified=True,
                        is_sudo=True,
                    )
                    session.add(admin)
                    await session.commit()
                    logger.info("admin_bootstrapped", username=settings.admin_username)
                else:
                    logger.info("admin_exists_skip", username=settings.admin_username)
        except IntegrityError:
            logger.info("admin_bootstrap_skip_race", username=settings.admin_username)
        except Exception:
            logger.exception("admin_bootstrap_failed", username=settings.admin_username)

    app.state.xlink = AppState(
        settings=settings,
        db=db,
        cache=cache,
        providers=providers,
        events=events,
        dispatcher=dispatcher,
        cleanup_job=cleanup_job,
        metrics_job=metrics_job,
        traffic_retention_job=traffic_retention_job,
        traffic_rollup_job=traffic_rollup_job,
        agent_reconcile_job=agent_reconcile_job,
        assignment_expiration_job=assignment_expiration_job,
        notification_job=notification_job,
        node_agent_scheduler=node_agent_scheduler,
        backup_job=backup_job,
        cert_renewal_job=cert_renewal_job,
        audit_writer=audit_writer,
        domain_metrics_collector=domain_metrics_collector,
        queue=queue,
    )
    logger.info("startup_complete")

    try:
        yield
    finally:
        logger.info("shutdown_begin")
        if leader is not None:
            await leader.stop()
        if grpc_server is not None:
            await grpc_server.stop()
        if cleanup_job is not None:
            await cleanup_job.stop()
        if metrics_job is not None:
            await metrics_job.stop()
        if traffic_retention_job is not None:
            await traffic_retention_job.stop()
        if traffic_rollup_job is not None:
            await traffic_rollup_job.stop()
        if agent_reconcile_job is not None:
            await agent_reconcile_job.stop()
        if assignment_expiration_job is not None:
            await assignment_expiration_job.stop()
        if notification_job is not None:
            await notification_job.stop()
        if node_agent_scheduler is not None:
            await node_agent_scheduler.stop()
        if backup_job is not None:
            await backup_job.stop()
        if cert_renewal_job is not None:
            await cert_renewal_job.stop()
        if domain_metrics_collector is not None:
            await domain_metrics_collector.stop()
        if audit_writer is not None:
            await audit_writer.stop()
        await events.drain()
        if queue is not None:
            await queue.stop()
        await dispatcher.drain()
        await cache.close()
        await db.dispose()
        logger.info("shutdown_complete")
