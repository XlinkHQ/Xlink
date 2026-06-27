from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.domain.node import Node, NodeStatus
from app.repositories.base import BaseRepository
from app.repositories.conflicts import conflict_from_integrity


def _conflict_from_integrity(exc: IntegrityError) -> ConflictError:
    return conflict_from_integrity(
        exc,
        [
            (
                ("uq_nodes_slug", "nodes.slug", "slug"),
                "Node slug already exists.",
                "slug_taken",
            ),
        ],
        "Node already exists.",
        "node_conflict",
    )


class NodeRepository(BaseRepository[Node]):
    model = Node

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_slug(self, slug: str) -> Node | None:
        return await self.get_by(slug=slug)

    async def save(self, node: Node) -> Node:
        await self.session.flush()
        await self.session.refresh(node)
        return node

    async def create_node(self, node: Node) -> Node:
        try:
            async with self.session.begin_nested():
                self.session.add(node)
                await self.session.flush()
        except IntegrityError as exc:
            raise _conflict_from_integrity(exc) from exc
        return node

    async def list_keyset(
        self,
        *,
        limit: int,
        cursor: tuple[datetime, uuid.UUID] | None = None,
        status: NodeStatus | None = None,
    ) -> Sequence[Node]:
        stmt = select(Node)
        if status is not None:
            stmt = stmt.where(Node.status == status)
        if cursor is not None:
            cursor_created_at, cursor_id = cursor
            stmt = stmt.where(
                tuple_(Node.created_at, Node.id) < tuple_(cursor_created_at, cursor_id)
            )
        stmt = stmt.order_by(Node.created_at.desc(), Node.id.desc()).limit(limit)
        return (await self.session.execute(stmt)).scalars().all()
