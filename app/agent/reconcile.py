from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from app.agent.command_service import CommandService
from app.agent.commands import CommandSigner
from app.agent.config_sync import ConfigSyncService
from app.agent.domain import DriftSeverity
from app.agent.healing import AutoUpgradeService, HealingPolicy, SelfHealingService
from app.core.leader import LeaderElector
from app.core.logging import get_logger
from app.db.redis import RedisCache
from app.db.session import Database
from app.domain.node import Node, NodeStatus
from app.events.bus import EventBus
from app.webhooks.dispatcher import WebhookDispatcher

logger = get_logger("xlink.agent.reconcile")

_BATCH_SIZE = 100


def _shift_calendar(dt: datetime, *, months: int = 0, years: int = 0) -> datetime:
    total = (dt.year + years) * 12 + (dt.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    import calendar

    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _reset_cutoffs(now: datetime) -> dict[str, datetime]:
    return {
        "day": now - timedelta(days=1),
        "week": now - timedelta(weeks=1),
        "month": _shift_calendar(now, months=-1),
        "year": _shift_calendar(now, years=-1),
    }


async def _apply_data_resets(session) -> list:
    from sqlalchemy import or_

    from app.domain.client_assignment import AssignmentStatus, ClientAssignment
    from app.domain.user import DataResetStrategy, User

    now = datetime.now(UTC)
    woke_nodes: set = set()
    changed = False

    for strategy, cutoff in _reset_cutoffs(now).items():
        due_stmt = select(User.id).where(
            User.data_reset_strategy == DataResetStrategy(strategy),
            or_(
                User.last_reset_at.is_(None),
                User.last_reset_at < cutoff,
            ),
            func.coalesce(User.last_reset_at, User.created_at) < cutoff,
        )
        due_ids = [uid for (uid,) in (await session.execute(due_stmt)).all()]
        if not due_ids:
            continue
        changed = True

        node_rows = await session.execute(
            select(ClientAssignment.node_id).where(
                ClientAssignment.user_id.in_(due_ids),
                ClientAssignment.status == AssignmentStatus.LIMITED,
            )
        )
        woke_nodes.update(nid for (nid,) in node_rows.all() if nid is not None)

        await session.execute(
            update(ClientAssignment)
            .where(ClientAssignment.user_id.in_(due_ids))
            .values(used_bytes=0)
        )
        await session.execute(
            update(ClientAssignment)
            .where(
                ClientAssignment.user_id.in_(due_ids),
                ClientAssignment.status == AssignmentStatus.LIMITED,
            )
            .values(status=AssignmentStatus.ACTIVE)
        )
        await session.execute(
            update(User).where(User.id.in_(due_ids)).values(users_data_usage=0, last_reset_at=now)
        )

    if changed and woke_nodes:
        active_count = (
            select(func.count())
            .select_from(ClientAssignment)
            .where(
                ClientAssignment.node_id == Node.id,
                ClientAssignment.status == AssignmentStatus.ACTIVE,
            )
            .scalar_subquery()
        )
        await session.execute(
            update(Node)
            .where(Node.id.in_(sorted(woke_nodes)))
            .values(current_users=active_count)
            .execution_options(synchronize_session=False)
        )

    if changed:
        await session.commit()
    return sorted(woke_nodes)


async def reconcile_once(
    db: Database,
    *,
    signer: CommandSigner,
    events: EventBus | None,
    self_healing_enabled: bool,
    target_version: str | None,
    batch_size: int = _BATCH_SIZE,
    cache: RedisCache | None = None,
    dispatcher: WebhookDispatcher | None = None,
) -> dict[str, int]:
    drifted = 0
    healed = 0
    upgrades = 0
    async with db.session() as session:
        reset_nodes = await _apply_data_resets(session)
        if reset_nodes and cache is not None:
            await cache.incr("subscription:rev:__global__")
            for nid in reset_nodes:
                await cache.publish_node_event(nid, "config_changed")
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
            config = configs.get(node.id, {"clients": [], "client_count": 0, "core_templates": {}})
            config["restart_nonce"] = node.node_metadata.get("restart_nonce", 0)
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
        cache: RedisCache | None = None,
        dispatcher: WebhookDispatcher | None = None,
        leader: LeaderElector | None = None,
    ) -> None:
        self._db = db
        self._signer = signer
        self._events = events
        self._interval = interval_seconds
        self._self_healing_enabled = self_healing_enabled
        self._target_version = target_version
        self._cache = cache
        self._dispatcher = dispatcher
        self._leader = leader
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
            if self._leader is not None and not self._leader.is_leader:
                continue
            try:
                await reconcile_once(
                    self._db,
                    signer=self._signer,
                    events=self._events,
                    self_healing_enabled=self._self_healing_enabled,
                    target_version=self._target_version,
                    cache=self._cache,
                    dispatcher=self._dispatcher,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("agent_reconcile_failed")
