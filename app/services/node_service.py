from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.pagination import decode_cursor, encode_cursor
from app.domain.node import Node, NodeStatus
from app.repositories.node import NodeRepository
from app.schemas.node import NodeCreate, NodeUpdate
from app.schemas.pagination import CursorParams
from app.services._shared import invalidate_subscription_cache, save_or_conflict


class NodeService:
    def __init__(self, repo: NodeRepository, subscription_service=None) -> None:  # noqa: ANN001
        self._repo = repo
        # Host, port and status all change what feeds contain; without this a
        # disabled or moved node stayed in cached subscriptions until expiry.
        self._subscription_service = subscription_service

    async def _changed(self, node_id: uuid.UUID) -> None:
        await invalidate_subscription_cache(self._subscription_service, node_id)

    async def create(self, data: NodeCreate) -> Node:
        node = Node(
            name=data.name,
            slug=data.slug,
            host=data.host,
            port=data.port,
            max_users=data.max_users,
            usage_coefficient=data.usage_coefficient,
            node_metadata=data.metadata,
            status=NodeStatus.OFFLINE,
        )
        return await self._repo.create_node(node)

    async def get(self, node_id: uuid.UUID) -> Node:
        node = await self._repo.get(node_id)
        if node is None:
            raise NotFoundError("Node not found.", code="node_not_found")
        return node

    async def update(self, node_id: uuid.UUID, data: NodeUpdate) -> Node:
        node = await self.get(node_id)
        if data.expected_version is not None and data.expected_version != node.version:
            raise ConflictError("Node was modified concurrently.", code="version_conflict")

        if data.name is not None:
            node.name = data.name
        if data.host is not None:
            node.host = data.host
        if data.port is not None:
            node.port = data.port
        if data.max_users is not None:
            node.max_users = data.max_users
        if data.usage_coefficient is not None:
            node.usage_coefficient = data.usage_coefficient
        if data.metadata is not None:
            node.node_metadata = data.metadata
        if data.socks_enabled is not None:
            node.socks_enabled = data.socks_enabled
        if data.socks_address is not None:
            node.socks_address = data.socks_address or None
        if data.socks_username is not None:
            node.socks_username = data.socks_username or None
        if data.socks_password is not None:
            node.socks_password = data.socks_password or None

        flushed = await self._flush(node)
        await self._changed(node_id)
        return flushed

    async def set_status(self, node_id: uuid.UUID, status: NodeStatus) -> Node:
        node = await self.get(node_id)
        previous = node.status
        node.status = status
        flushed = await self._flush(node)
        if previous != status:
            await self._changed(node_id)
        return flushed

    async def disable(self, node_id: uuid.UUID) -> Node:
        return await self.set_status(node_id, NodeStatus.DISABLED)

    async def delete(self, node_id: uuid.UUID) -> None:
        from sqlalchemy import func, select, update

        from app.domain.client_assignment import ClientAssignment
        from app.domain.user import User

        node = await self.get(node_id)
        session = self._repo.session
        affected = set(
            (
                await session.execute(
                    select(ClientAssignment.user_id).where(ClientAssignment.node_id == node_id)
                )
            )
            .scalars()
            .all()
        )
        await self._repo.delete(node)
        if affected:
            await session.flush()
            total = (
                select(func.coalesce(func.sum(ClientAssignment.used_bytes), 0))
                .where(ClientAssignment.user_id == User.id)
                .scalar_subquery()
            )
            await session.execute(
                update(User)
                .where(User.id.in_(affected))
                .values(users_data_usage=total)
                .execution_options(synchronize_session=False)
            )
            await session.flush()
        if self._subscription_service is not None:
            await self._subscription_service.invalidate_cache()

    async def heartbeat(
        self,
        node_id: uuid.UUID,
        current_users: int,
        status: NodeStatus | None = None,
    ) -> Node:
        node = await self.get(node_id)
        metadata = dict(node.node_metadata)
        metadata["agent_reported_users"] = current_users
        node.node_metadata = metadata
        node.last_seen_at = datetime.now(UTC)
        if status is not None:
            node.status = status
        elif node.status is NodeStatus.OFFLINE:
            node.status = NodeStatus.ACTIVE
        return await self._flush(node)

    async def provision_agent_token(self, node_id: uuid.UUID) -> str:
        node = await self.get(node_id)
        token = secrets.token_urlsafe(32)
        metadata = dict(node.node_metadata)

        metadata["agent_token_hash"] = hashlib.sha256(token.encode("utf-8")).hexdigest()
        node.node_metadata = metadata
        await self._flush(node)
        return token

    async def restart_core(self, node_id: uuid.UUID) -> Node:
        node = await self.get(node_id)
        metadata = dict(node.node_metadata)
        metadata["restart_nonce"] = int(metadata.get("restart_nonce", 0)) + 1
        node.node_metadata = metadata
        await self._flush(node)
        return node

    async def list_nodes_keyset(
        self,
        params: CursorParams,
        *,
        status: NodeStatus | None = None,
    ) -> tuple[list[Node], str | None]:
        cursor = None
        if params.cursor is not None:
            try:
                cursor = decode_cursor(params.cursor)
            except ValueError as exc:
                raise ValidationError(str(exc), code="invalid_cursor") from exc

        rows = list(
            await self._repo.list_keyset(limit=params.limit + 1, cursor=cursor, status=status)
        )

        next_cursor = None
        if len(rows) > params.limit:
            rows = rows[: params.limit]
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)
        return rows, next_cursor

    async def _flush(self, node: Node) -> Node:
        return await save_or_conflict(self._repo.save, node, "Node")
