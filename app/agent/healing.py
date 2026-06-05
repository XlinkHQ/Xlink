from __future__ import annotations

from dataclasses import dataclass

from app.agent.command_service import CommandService
from app.agent.config_sync import ConfigSyncService
from app.agent.domain import CommandKind, DriftSeverity, NodeCommand, NodeDriftReport
from app.core.logging import get_logger
from app.domain.node import Node

logger = get_logger("xlink.agent.healing")

_DESIRED_VERSION_KEY = "desired_config_version"
_AGENT_VERSION_KEY = "reported_state"
_TARGET_AGENT_VERSION_KEY = "target_agent_version"


@dataclass(frozen=True, slots=True)
class HealingPolicy:
    enabled: bool = True
    heal_on: tuple[DriftSeverity, ...] = (DriftSeverity.MEDIUM, DriftSeverity.HIGH)


class SelfHealingService:
    def __init__(
        self,
        config_sync: ConfigSyncService,
        commands: CommandService,
        *,
        policy: HealingPolicy | None = None,
    ) -> None:
        self._config_sync = config_sync
        self._commands = commands
        self._policy = policy or HealingPolicy()

    async def reconcile(self, node: Node) -> NodeDriftReport:
        report = await self._config_sync.detect_drift(node)
        return await self._maybe_heal(node, report)

    async def reconcile_with_config(self, node: Node, config: dict) -> NodeDriftReport:
        report = await self._config_sync.detect_drift_with_config(node, config)
        return await self._maybe_heal(node, report)

    async def _maybe_heal(self, node: Node, report: NodeDriftReport) -> NodeDriftReport:
        if not self._policy.enabled or report.severity not in self._policy.heal_on:
            return report
        command = await self._commands.enqueue_unique(
            node,
            kind=CommandKind.APPLY_CONFIG.value,
            payload={"config_version": report.desired_version},
            origin="self_healing",
        )
        if command is not None:
            report.remediated = True
            logger.info(
                "self_healing_command_issued",
                node_id=str(node.id),
                severity=report.severity.value,
                command_id=str(command.id),
            )
        return report


class AutoUpgradeService:
    def __init__(self, commands: CommandService) -> None:
        self._commands = commands

    def _current_agent_version(self, node: Node) -> str | None:
        state = node.node_metadata.get(_AGENT_VERSION_KEY)
        if isinstance(state, dict):
            value = state.get("agent_version")
            return value if isinstance(value, str) else None
        return None

    async def ensure_target(self, node: Node, *, target_version: str) -> NodeCommand | None:
        current = self._current_agent_version(node)
        if current == target_version:
            return None
        return await self._commands.enqueue_unique(
            node,
            kind=CommandKind.UPGRADE.value,
            payload={"target_version": target_version, "from_version": current},
            origin="auto_upgrade",
        )

    async def rollback(self, node: Node, *, target_version: str) -> NodeCommand:
        return await self._commands.enqueue(
            node,
            kind=CommandKind.ROLLBACK.value,
            payload={"target_version": target_version},
            origin="auto_upgrade",
        )
