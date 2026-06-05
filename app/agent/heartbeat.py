from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime

from app.core.exceptions import AuthenticationError, NotFoundError
from app.domain.node import Node, NodeStatus
from app.events.bus import EventBus
from app.events.models import NodeOffline, NodeRecovered
from app.repositories.node import NodeRepository

_TOKEN_HASH_KEY = "agent_token_hash"


def hash_agent_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class NodeHeartbeatService:
    def __init__(self, nodes: NodeRepository, events: EventBus | None = None) -> None:
        self._nodes = nodes
        self._events = events

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
        node.node_metadata = metadata
        node.current_users = current_users
        node.last_seen_at = datetime.now(UTC)
        node.status = status
        saved = await self._nodes.save(node)
        recovered = previous_status is NodeStatus.OFFLINE and status is NodeStatus.ACTIVE
        if self._events is not None and recovered:
            await self._events.publish(NodeRecovered(node_id=node_id))
        return saved

    async def health_check(self, node_id: uuid.UUID, *, token: str) -> bool:
        node = await self.authenticate(node_id, token)
        return node.status is not NodeStatus.DISABLED

    async def mark_stale_offline(self, node: Node) -> Node:
        if node.status is not NodeStatus.ACTIVE:
            return node
        node.status = NodeStatus.OFFLINE
        saved = await self._nodes.save(node)
        if self._events is not None:
            await self._events.publish(NodeOffline(node_id=node.id, reason="heartbeat_stale"))
        return saved

    async def _get_node(self, node_id: uuid.UUID) -> Node:
        node = await self._nodes.get(node_id)
        if node is None:
            raise NotFoundError("Node not found.", code="node_not_found")
        return node
