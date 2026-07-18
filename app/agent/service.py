from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.command_service import CommandService
from app.agent.commands import CommandSigner
from app.agent.config_sync import ConfigSyncService
from app.agent.domain import NodeCommand, NodeDriftReport, NodeProviderHealth
from app.agent.healing import AutoUpgradeService, HealingPolicy, SelfHealingService
from app.agent.heartbeat import NodeHeartbeatService
from app.agent.models import AgentHeartbeat, RetryPolicy, SyncBatch, SyncCursor
from app.agent.provider_health import ProviderHealthService
from app.agent.streaming import AgentStreamService
from app.agent.sync import NodeSyncService
from app.core.cache import CacheProtocol
from app.core.exceptions import ConfigurationError
from app.domain.node import Node, NodeStatus
from app.events.bus import EventBus
from app.repositories.node import NodeRepository
from app.traffic.schemas import TrafficBatch, TrafficIngestResult
from app.traffic.service import TrafficService


class NodeAgentService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        events: EventBus | None = None,
        retry: RetryPolicy | None = None,
        signer: CommandSigner | None = None,
        cache: CacheProtocol | None = None,
        healing_policy: HealingPolicy | None = None,
    ) -> None:
        self._session = session
        self._nodes = NodeRepository(session)
        self._heartbeat = NodeHeartbeatService(self._nodes, events)
        self._sync = NodeSyncService(session, retry)
        self._traffic = TrafficService(session, events=events, cache=cache)
        self._config_sync = ConfigSyncService(session)
        self._provider_health = ProviderHealthService(session, events=events)
        self._signer = signer
        self._cache = cache
        self._events = events
        self._healing_policy = healing_policy
        if signer is not None:
            self._commands = CommandService(session, signer=signer, events=events)
            self._healing = SelfHealingService(
                self._config_sync, self._commands, policy=healing_policy
            )
            self._upgrade = AutoUpgradeService(self._commands)
        else:
            self._commands = None
            self._healing = None
            self._upgrade = None
        self._stream = AgentStreamService(cache) if cache is not None else None

    async def authenticate(self, node_id: uuid.UUID, token: str) -> Node:
        return await self._heartbeat.authenticate(node_id, token)

    async def heartbeat(self, heartbeat: AgentHeartbeat, *, token: str) -> Node:
        status = NodeStatus.ACTIVE if heartbeat.status.value == "healthy" else NodeStatus.OFFLINE
        return await self._heartbeat.heartbeat(
            heartbeat.node_id,
            token=token,
            current_users=heartbeat.stats.current_users,
            status=status,
            stats={
                "cpu_percent": heartbeat.stats.cpu_percent,
                "memory_percent": heartbeat.stats.memory_percent,
                "rx_bytes": heartbeat.stats.rx_bytes,
                "tx_bytes": heartbeat.stats.tx_bytes,
                "observed_at": heartbeat.observed_at.isoformat(),
            },
        )

    async def health_check(self, node_id: uuid.UUID, *, token: str) -> bool:
        return await self._heartbeat.health_check(node_id, token=token)

    async def assignment_sync(
        self,
        node_id: uuid.UUID,
        *,
        token: str,
        cursor: SyncCursor | None = None,
        limit: int = 100,
    ) -> SyncBatch:
        await self.authenticate(node_id, token)
        return await self._sync.assignment_sync(node_id, cursor=cursor, limit=limit)

    async def report_traffic(
        self,
        node_id: uuid.UUID,
        *,
        token: str,
        batch: TrafficBatch,
    ) -> TrafficIngestResult:
        await self.authenticate(node_id, token)
        return await self.ingest_traffic(node_id, batch)

    async def ingest_traffic(
        self, node_id: uuid.UUID, batch: TrafficBatch
    ) -> TrafficIngestResult:
        if batch.node_id != node_id:
            batch = TrafficBatch(node_id=node_id, batch_id=batch.batch_id, samples=batch.samples)
        return await self._traffic.ingest(batch)

    async def config_snapshot(
        self, node_id: uuid.UUID, *, token: str, known_version: str | None = None
    ) -> dict:
        node = await self.authenticate(node_id, token)
        return await self._config_sync.build_snapshot(
            node, cache=self._cache, known_version=known_version
        )

    async def report_state(
        self,
        node_id: uuid.UUID,
        *,
        token: str,
        config_version: str | None,
        agent_version: str | None,
        applied: dict,
        provider_status: dict,
    ) -> NodeDriftReport:
        node = await self.authenticate(node_id, token)

        node.last_seen_at = datetime.now(UTC)
        recovered = node.status is NodeStatus.OFFLINE
        if recovered:
            node.status = NodeStatus.ACTIVE
            # A config report is also a liveness signal — fire the SAME recovery
            # event + webhook the heartbeat path fires, so a node that comes back
            # via its config poll isn't silently un-alerted.
            await self._heartbeat.emit_recovery(node)
        await self._config_sync.record_reported_state(
            node,
            config_version_value=config_version,
            agent_version=agent_version,
            applied=applied,
            provider_status=provider_status,
        )
        return await self.reconcile(node)

    async def reconcile(self, node: Node) -> NodeDriftReport:
        if self._healing is not None:
            return await self._healing.reconcile(node)
        return await self._config_sync.detect_drift(node)

    async def enqueue_command(
        self,
        node_id: uuid.UUID,
        *,
        kind: str,
        payload: dict,
        origin: str = "operator",
        max_attempts: int = 3,
    ) -> NodeCommand:
        self._require_commands()
        node = await self._heartbeat._get_node(node_id)
        return await self._commands.enqueue(
            node, kind=kind, payload=payload, origin=origin, max_attempts=max_attempts
        )

    async def lease_commands(
        self, node_id: uuid.UUID, *, token: str, limit: int = 10
    ) -> tuple[str, list[NodeCommand]]:
        node = await self.authenticate(node_id, token)
        self._require_commands()
        return await self._commands.lease(node, limit=limit)

    async def report_command_result(
        self,
        node_id: uuid.UUID,
        *,
        token: str,
        command_id: uuid.UUID,
        lease_token: str,
        success: bool,
        result: dict,
    ) -> NodeCommand:
        await self.authenticate(node_id, token)
        self._require_commands()
        return await self._commands.report_result(
            command_id, node_id=node_id, lease_token=lease_token, success=success, result=result
        )

    async def ensure_upgrade(
        self, node_id: uuid.UUID, *, target_version: str
    ) -> NodeCommand | None:
        self._require_commands()
        node = await self._heartbeat._get_node(node_id)
        return await self._upgrade.ensure_target(node, target_version=target_version)

    async def record_provider_health(
        self, node_id: uuid.UUID, *, token: str, checks: list[dict]
    ) -> int:
        await self.authenticate(node_id, token)
        return await self._provider_health.record(node_id, checks)

    async def provider_health(self, node_id: uuid.UUID) -> list[NodeProviderHealth]:
        return list(await self._provider_health.latest(node_id))

    async def push_metrics(
        self, node_id: uuid.UUID, *, token: str, samples: list[dict]
    ) -> tuple[int, int]:
        await self.authenticate(node_id, token)
        self._require_stream()
        return await self._stream.push_metrics(node_id, samples)

    async def push_logs(
        self, node_id: uuid.UUID, *, token: str, lines: list[dict]
    ) -> tuple[int, int]:
        await self.authenticate(node_id, token)
        self._require_stream()
        return await self._stream.push_logs(node_id, lines)

    async def read_metrics(self, node_id: uuid.UUID, *, limit: int = 100) -> list:
        self._require_stream()
        return await self._stream.read_metrics(node_id, limit=limit)

    async def read_logs(self, node_id: uuid.UUID, *, limit: int = 100) -> list:
        self._require_stream()
        return await self._stream.read_logs(node_id, limit=limit)

    def _require_commands(self) -> None:
        if self._commands is None:
            raise ConfigurationError(
                "Command signer is not configured.", code="agent_commands_unconfigured"
            )

    def _require_stream(self) -> None:
        if self._stream is None:
            raise ConfigurationError(
                "Stream cache is not configured.", code="agent_stream_unconfigured"
            )

    async def with_retry[T](self, operation: Callable[[], Awaitable[T]]) -> T:
        return await self._sync.with_retry(operation)
