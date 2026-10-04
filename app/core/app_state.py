"""`AppState` lives here, not in `lifespan`, so that `dependencies/core.py` can
depend on the state shape without importing the module that builds it.

`core/lifespan` imports services; `dependencies/core` imports `AppState`. With
both in one module that is a latent cycle, held together only by lifespan's lazy
in-function imports. Splitting the dataclass out breaks it structurally.

`lifespan` re-exports `AppState`, so existing `from app.core.lifespan import
AppState` imports keep working.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agent.reconcile import AgentReconcileJob
from app.agent.scheduler import NodeAgentScheduler
from app.backup.scheduler import BackupJob
from app.core.config import Settings
from app.core.jobs import AssignmentExpirationJob, TokenCleanupJob
from app.core.queue import DurableQueue
from app.db.redis import RedisCache
from app.db.session import Database
from app.events.bus import EventBus
from app.middleware.audit_writer import AuditWriter
from app.monitoring.summary import MetricsRefreshJob
from app.notifications.job import NotificationJob
from app.observability.collector import DomainMetricsCollector
from app.providers.base.registry import ProviderRegistry
from app.services.cert_renewal import CertRenewalJob
from app.traffic.scheduler import TrafficRetentionJob, TrafficRollupJob
from app.webhooks.dispatcher import WebhookDispatcher


@dataclass(slots=True)
class AppState:
    settings: Settings
    db: Database
    cache: RedisCache
    providers: ProviderRegistry
    events: EventBus
    dispatcher: WebhookDispatcher | None = None
    cleanup_job: TokenCleanupJob | None = None
    metrics_job: MetricsRefreshJob | None = None
    traffic_retention_job: TrafficRetentionJob | None = None
    traffic_rollup_job: TrafficRollupJob | None = None
    agent_reconcile_job: AgentReconcileJob | None = None
    assignment_expiration_job: AssignmentExpirationJob | None = None
    notification_job: NotificationJob | None = None
    node_agent_scheduler: NodeAgentScheduler | None = None
    backup_job: BackupJob | None = None
    cert_renewal_job: CertRenewalJob | None = None
    audit_writer: AuditWriter | None = None
    domain_metrics_collector: DomainMetricsCollector | None = None
    queue: DurableQueue | None = None

