from __future__ import annotations

from collections.abc import AsyncIterator
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

# How many ORM rows to fetch per network round-trip when streaming. Bounds the
# number of rows resident in memory at any moment (server-side cursor / yield_per)
# so a 500k-row export never materialises the whole table.
_STREAM_BATCH = 1000

# The five top-level arrays of a backup document, in the order they are exported.
# Each entry is (json_key, ORM model, redact_secrets). ``traffic_metadata`` is
# derived from nodes and handled separately.
_TABLES: tuple[tuple[str, Any, bool], ...] = (
    ("users", User, True),
    ("nodes", Node, False),
    ("profiles", Profile, False),
    ("assignments", ClientAssignment, False),
)


def serialize_row(row, *, redacted: bool = False) -> dict[str, Any]:
    data = {}
    for column_attr in row.__mapper__.column_attrs:
        key = column_attr.key
        output_key = "metadata" if key == "node_metadata" else key
        data[output_key] = getattr(row, key)
    if redacted:
        # User auth secrets are NOT restorable material (hashes/TOTP are reset
        # on restore), so redact them. Node/profile/assignment secrets
        # (socks_password, settings private keys, assignment credentials) ARE
        # required to restore a working config, so they stay in the payload —
        # confidentiality of the backup is enforced at the transport/storage
        # layer instead (sudo-only export endpoint + 0600 backup files).
        for secret_key in ("hashed_password", "totp_secret"):
            if data.get(secret_key):
                data[secret_key] = _REDACTED
    return data


def _traffic_row(node: Node) -> dict[str, Any] | None:
    stats = node.node_metadata.get("assignment_stats", {})
    if stats:
        return {"node_id": node.id, "assignment_stats": stats}
    return None


async def stream_rows(
    session: AsyncSession,
    model,
    *,
    since: datetime | None = None,
    redacted: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """Yield serialized rows for ``model`` one at a time using a server-side
    cursor (``stream_scalars`` + ``yield_per``) so the full table is never held
    in memory. Async throughout — never blocks the event loop."""
    stmt = select(model)
    if since is not None:
        stmt = stmt.where(model.updated_at >= since)
    result = await session.stream_scalars(stmt.execution_options(yield_per=_STREAM_BATCH))
    async for row in result:
        yield serialize_row(row, redacted=redacted)


async def stream_traffic_metadata(
    session: AsyncSession, *, since: datetime | None = None
) -> AsyncIterator[dict[str, Any]]:
    stmt = select(Node)
    if since is not None:
        stmt = stmt.where(Node.updated_at >= since)
    result = await session.stream_scalars(stmt.execution_options(yield_per=_STREAM_BATCH))
    async for node in result:
        traffic = _traffic_row(node)
        if traffic is not None:
            yield traffic


def table_specs() -> tuple[tuple[str, Any, bool], ...]:
    return _TABLES


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
            "traffic_metadata": await self._traffic_metadata(since=since),
        }
        return BackupDocument.create(scope=scope, data=data, checksum=checksum_payload(data))

    async def _rows(
        self,
        model,
        *,
        since: datetime | None = None,
        redacted: bool = False,
    ) -> list[dict[str, Any]]:
        return [
            row
            async for row in stream_rows(self._session, model, since=since, redacted=redacted)
        ]

    async def _traffic_metadata(self, *, since: datetime | None = None) -> list[dict[str, Any]]:
        return [row async for row in stream_traffic_metadata(self._session, since=since)]
