from __future__ import annotations

import hmac
import uuid
from datetime import UTC, datetime

from app.core.exceptions import AuthenticationError, NotFoundError
from app.core.security import hash_token as hash_agent_token
from app.domain.node import Node, NodeStatus
from app.events.bus import EventBus
from app.events.models import NodeOffline, NodeRecovered
from app.repositories.node import NodeRepository
from app.webhooks import events as webhook_events
from app.webhooks.dispatcher import WebhookDispatcher

_TOKEN_HASH_KEY = "agent_token_hash"


class NodeHeartbeatService:
    def __init__(
        self,
        nodes: NodeRepository,
        events: EventBus | None = None,
        dispatcher: WebhookDispatcher | None = None,
    ) -> None:
        self._nodes = nodes
        self._events = events
        self._dispatcher = dispatcher

    async def _node_alerts_enabled(self) -> bool:
        from app.domain.app_settings import AppSettings

        row = await self._nodes.session.get(AppSettings, 1)
        if row is None:
            return True
        if not (row.notify_enabled and row.notify_node_down):
            return False
        if self._dispatcher is not None:
            self._dispatcher.apply_overrides(
                webhook_address=row.webhook_address,
                discord_webhook_url=row.discord_webhook_url,
                telegram_bot_token=row.telegram_bot_token,
                telegram_chat_ids=row.telegram_chat_ids,
            )
        return True

    async def authenticate(self, node_id: uuid.UUID, token: str) -> Node:
        node = await self._get_node(node_id)
        expected = node.node_metadata.get(_TOKEN_HASH_KEY)
        if not isinstance(expected, str) or not expected:
            raise AuthenticationError(
                "Node agent token is not configured.", code="node_auth_failed"
            )
        if not hmac.compare_digest(expected, hash_agent_token(token)):
            raise AuthenticationError("Invalid node agent token.", code="node_auth_failed")
        return node

    async def heartbeat(
        self,
        node_id: uuid.UUID,
        *,
        token: str,
        current_users: int,
        status: NodeStatus = NodeStatus.ACTIVE,
        stats: dict | None = None,
    ) -> Node:
        node = await self.authenticate(node_id, token)
        previous_status = node.status
        metadata = dict(node.node_metadata)
        if stats:
            metadata["agent_stats"] = dict(stats)
        # current_users is DB-authoritative (COUNT of ACTIVE assignments,
        # maintained by every assignment-status writer). The agent-observed
        # client count is telemetry only — keep it in metadata, never overwrite
        # the authoritative counter, or heartbeats clobber the real count.
        metadata["agent_reported_users"] = current_users
        node.node_metadata = metadata
        node.last_seen_at = datetime.now(UTC)
        node.status = status
        saved = await self._nodes.save(node)
        if previous_status is NodeStatus.OFFLINE and status is NodeStatus.ACTIVE:
            await self.emit_recovery(saved)
        return saved

    async def emit_recovery(self, node: Node) -> None:
        """Publish the NodeRecovered event + webhook for an OFFLINE→ACTIVE
        transition. Shared so every path that brings a node back (heartbeat AND
        the config report_state path) fires the identical notification instead
        of one silently skipping it."""
        if self._events is not None:
            await self._events.publish(NodeRecovered(node_id=node.id))
        if self._dispatcher is not None and await self._node_alerts_enabled():
            await self._dispatcher.dispatch(
                webhook_events.NODE_RECOVERED,
                node.name,
                detail=f"Node '{node.name}' ({node.host}) recovered",
            )

    async def health_check(self, node_id: uuid.UUID, *, token: str) -> bool:
        node = await self.authenticate(node_id, token)
        return node.status is not NodeStatus.DISABLED

    async def mark_stale_offline(self, node: Node) -> Node:
        if node.status is not NodeStatus.ACTIVE:
            return node
        node.status = NodeStatus.OFFLINE
        saved = await self._nodes.save(node)
        if self._events is not None:
            # Dispatch off the offline-detection path: NodeOffline triggers
            # auto-failover (many provider create_client calls). Running it inline
            # blocks the detector loop and holds its DB session open for the whole
            # migration when a large node drops.
            self._events.publish_background(NodeOffline(node_id=node.id, reason="heartbeat_stale"))
        if self._dispatcher is not None and await self._node_alerts_enabled():
            await self._dispatcher.dispatch(
                webhook_events.NODE_DOWN,
                saved.name,
                detail=f"Node '{saved.name}' ({saved.host}) went offline",
            )
        return saved

    async def _get_node(self, node_id: uuid.UUID) -> Node:
        node = await self._nodes.get(node_id)
        if node is None:
            raise NotFoundError("Node not found.", code="node_not_found")
        return node
