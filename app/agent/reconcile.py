from __future__ import annotations

import asyncio
import contextlib

from sqlalchemy import select

from app.agent.command_service import CommandService
from app.agent.commands import CommandSigner
from app.agent.config_sync import ConfigSyncService
from app.agent.domain import DriftSeverity
from app.agent.healing import AutoUpgradeService, HealingPolicy, SelfHealingService
from app.core.logging import get_logger
from app.db.session import Database
from app.domain.node import Node, NodeStatus
from app.events.bus import EventBus

logger = get_logger("xlink.agent.reconcile")

_BATCH_SIZE = 100


async def reconcile_once(
    db: Database,
    *,
    signer: CommandSigner,
    events: EventBus | None,
    self_healing_enabled: bool,
    target_version: str | None,
    batch_size: int = _BATCH_SIZE,
) -> dict[str, int]:
    drifted = 0
    healed = 0
    upgrades = 0
    async with db.session() as session:
        node_ids = (
            (await session.execute(select(Node.id).where(Node.status == NodeStatus.ACTIVE)))
            .scalars()
            .all()
        )

    size = max(1, batch_size)
    for start in range(0, len(node_ids), size):
        batch_ids = list(node_ids[start : start + size])
        stats = await _reconcile_batch(
            db,
            batch_ids,
            signer=signer,
            events=events,
            self_healing_enabled=self_healing_enabled,
            target_version=target_version,
        )
        drifted += stats["drifted"]
        healed += stats["healed"]
        upgrades += stats["upgrades"]

    if drifted or upgrades:
        logger.info("reconcile_cycle", drifted=drifted, healed=healed, upgrades=upgrades)
    return {"drifted": drifted, "healed": healed, "upgrades": upgrades}


async def _reconcile_batch(
    db: Database,
    node_ids: list,
    *,
    signer: CommandSigner,
    events: EventBus | None,
    self_healing_enabled: bool,
    target_version: str | None,
) -> dict[str, int]:
    drifted = 0
    healed = 0
    upgrades = 0
    async with db.session() as session:
        nodes = (await session.execute(select(Node).where(Node.id.in_(node_ids)))).scalars().all()
        config_sync = ConfigSyncService(session)
        commands = CommandService(session, signer=signer, events=events)
        healing = SelfHealingService(
            config_sync, commands, policy=HealingPolicy(enabled=self_healing_enabled)
        )
        upgrade = AutoUpgradeService(commands)
        configs = await config_sync.desired_configs_for_nodes([n.id for n in nodes])
        for node in nodes:
            config = configs.get(node.id, {"clients": [], "client_count": 0})
            report = await healing.reconcile_with_config(node, config)
            if report.severity is not DriftSeverity.NONE:
                drifted += 1
            if report.remediated:
                healed += 1
            if target_version is not None:
                command = await upgrade.ensure_target(node, target_version=target_version)
                if command is not None:
                    upgrades += 1
    return {"drifted": drifted, "healed": healed, "upgrades": upgrades}


class AgentReconcileJob:
    def __init__(
        self,
        db: Database,
        *,
        signer: CommandSigner,
        events: EventBus | None = None,
        interval_seconds: int,
        self_healing_enabled: bool,
        target_version: str | None,
    ) -> None:
        self._db = db
        self._signer = signer
        self._events = events
        self._interval = interval_seconds
        self._self_healing_enabled = self_healing_enabled
        self._target_version = target_version
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="agent-reconcile")
        logger.info("agent_reconcile_started", interval_seconds=self._interval)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
        logger.info("agent_reconcile_stopped")

    async def _run(self) -> None:
        while not self._stopping.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            if self._stopping.is_set():
                break
            try:
                await reconcile_once(
                    self._db,
                    signer=self._signer,
                    events=self._events,
                    self_healing_enabled=self._self_healing_enabled,
                    target_version=self._target_version,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("agent_reconcile_failed")
