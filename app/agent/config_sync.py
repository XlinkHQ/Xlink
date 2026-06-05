from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

import orjson
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.domain import DriftSeverity, NodeDriftReport
from app.agent.repository import NodeDriftRepository
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node
from app.domain.profile import Profile
from app.gitops.diff import DiffEngine

_DESIRED_VERSION_KEY = "desired_config_version"
_REPORTED_VERSION_KEY = "reported_config_version"
_REPORTED_STATE_KEY = "reported_state"


def config_version(config: dict[str, Any]) -> str:
    raw = orjson.dumps(config, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(raw).hexdigest()[:32]


class ConfigSyncService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._drift = NodeDriftRepository(session)
        self._diff = DiffEngine()

    async def desired_configs_for_nodes(
        self, node_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dict[str, Any]]:
        if not node_ids:
            return {}
        result: dict[uuid.UUID, list[dict[str, Any]]] = {nid: [] for nid in node_ids}
        stmt = (
            select(ClientAssignment, Profile)
            .join(Profile, ClientAssignment.profile_id == Profile.id)
            .where(
                ClientAssignment.node_id.in_(node_ids),
                ClientAssignment.status == AssignmentStatus.ACTIVE,
            )
            .order_by(ClientAssignment.node_id, ClientAssignment.id.asc())
        )
        rows = (await self._session.execute(stmt)).all()
        for assignment, profile in rows:
            result.setdefault(assignment.node_id, []).append(
                {
                    "assignment_id": str(assignment.id),
                    "provider_client_id": assignment.provider_client_id,
                    "provider_kind": assignment.provider_kind.value,
                    "protocol": profile.protocol,
                    "profile_slug": profile.slug,
                    "settings": dict(profile.settings),
                }
            )
        return {
            nid: {"clients": clients, "client_count": len(clients)}
            for nid, clients in result.items()
        }

    async def desired_config(self, node_id: uuid.UUID) -> dict[str, Any]:
        stmt = (
            select(ClientAssignment, Profile)
            .join(Profile, ClientAssignment.profile_id == Profile.id)
            .where(
                ClientAssignment.node_id == node_id,
                ClientAssignment.status == AssignmentStatus.ACTIVE,
            )
            .order_by(ClientAssignment.id.asc())
        )
        rows = (await self._session.execute(stmt)).all()
        clients = [
            {
                "assignment_id": str(assignment.id),
                "provider_client_id": assignment.provider_client_id,
                "provider_kind": assignment.provider_kind.value,
                "protocol": profile.protocol,
                "profile_slug": profile.slug,
                "settings": dict(profile.settings),
            }
            for assignment, profile in rows
        ]
        return {"clients": clients, "client_count": len(clients)}

    async def build_snapshot(self, node: Node) -> dict[str, Any]:
        config = await self.desired_config(node.id)
        version = config_version(config)
        metadata = dict(node.node_metadata)
        if metadata.get(_DESIRED_VERSION_KEY) != version:
            metadata[_DESIRED_VERSION_KEY] = version
            node.node_metadata = metadata
            await self._session.flush()
        return {
            "node_id": node.id,
            "config_version": version,
            "config": config,
            "assignment_count": config["client_count"],
        }

    async def record_reported_state(
        self,
        node: Node,
        *,
        config_version_value: str | None,
        agent_version: str | None,
        applied: dict[str, Any],
        provider_status: dict[str, str],
    ) -> None:
        metadata = dict(node.node_metadata)
        metadata[_REPORTED_VERSION_KEY] = config_version_value
        metadata[_REPORTED_STATE_KEY] = {
            "agent_version": agent_version,
            "applied": applied,
            "provider_status": provider_status,
            "reported_at": datetime.now(UTC).isoformat(),
        }
        node.node_metadata = metadata
        await self._session.flush()

    async def detect_drift(self, node: Node) -> NodeDriftReport:
        config = await self.desired_config(node.id)
        return await self.detect_drift_with_config(node, config)

    async def detect_drift_with_config(self, node: Node, config: dict[str, Any]) -> NodeDriftReport:
        desired_version = config_version(config)
        metadata = dict(node.node_metadata)
        if metadata.get(_DESIRED_VERSION_KEY) != desired_version:
            metadata[_DESIRED_VERSION_KEY] = desired_version
            node.node_metadata = metadata
        reported_version = metadata.get(_REPORTED_VERSION_KEY)
        reported_state = metadata.get(_REPORTED_STATE_KEY) or {}
        applied = reported_state.get("applied", {}) if isinstance(reported_state, dict) else {}

        diff = self._diff.compare(applied, config)
        severity = self._severity(desired_version, reported_version, diff)
        report = NodeDriftReport(
            node_id=node.id,
            desired_version=desired_version,
            reported_version=reported_version if isinstance(reported_version, str) else None,
            severity=severity,
            drift={
                "added": diff.added,
                "changed": diff.changed,
                "removed": diff.removed,
            },
            detected_at=datetime.now(UTC),
            remediated=False,
        )
        return await self._drift.add(report)

    def _severity(self, desired_version: str, reported_version: Any, diff) -> DriftSeverity:
        if reported_version is None:
            return DriftSeverity.HIGH
        if reported_version == desired_version:
            return DriftSeverity.NONE
        changed = len(diff.added) + len(diff.changed) + len(diff.removed)
        if changed == 0:
            return DriftSeverity.LOW
        if changed <= 2:
            return DriftSeverity.MEDIUM
        return DriftSeverity.HIGH
