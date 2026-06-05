from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backup.models import BackupDocument, BackupScope
from app.backup.validator import checksum_payload
from app.domain.client_assignment import ClientAssignment
from app.domain.node import Node
from app.domain.profile import Profile
from app.domain.user import User

_REDACTED = "<redacted>"


class BackupExporter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def export(
        self, *, scope: BackupScope = BackupScope.FULL, since: datetime | None = None
    ) -> BackupDocument:
        data = {
            "users": await self._rows(User, since=since, redacted=True),
            "nodes": await self._rows(Node, since=since),
            "profiles": await self._rows(Profile, since=since),
            "assignments": await self._rows(ClientAssignment, since=since),
            "subscriptions": [],
            "traffic_metadata": await self._traffic_metadata(),
            "provider_metadata": [],
        }
        return BackupDocument.create(scope=scope, data=data, checksum=checksum_payload(data))

    async def _rows(
        self,
        model,
        *,
        since: datetime | None = None,
        redacted: bool = False,
    ) -> list[dict[str, Any]]:
        stmt = select(model)
        if since is not None:
            stmt = stmt.where(model.updated_at >= since)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._serialize(row, redacted=redacted) for row in rows]

    def _serialize(self, row, *, redacted: bool = False) -> dict[str, Any]:
        data = {}
        for column_attr in row.__mapper__.column_attrs:
            key = column_attr.key
            output_key = "metadata" if key == "node_metadata" else key
            data[output_key] = getattr(row, key)
        if redacted and "hashed_password" in data:
            data["hashed_password"] = _REDACTED
        return data

    async def _traffic_metadata(self) -> list[dict[str, Any]]:
        nodes = (await self._session.execute(select(Node))).scalars().all()
        rows = []
        for node in nodes:
            stats = node.node_metadata.get("assignment_stats", {})
            if stats:
                rows.append({"node_id": node.id, "assignment_stats": stats})
        return rows
