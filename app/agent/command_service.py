from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.commands import (
    CommandSigner,
    CommandValidationError,
    is_allowed_kind,
    validate_payload,
)
from app.agent.domain import CommandKind, CommandStatus, NodeCommand
from app.agent.repository import NodeCommandRepository
from app.core.exceptions import NotFoundError, ValidationError
from app.domain.node import Node
from app.events.bus import EventBus
from app.events.models import NodeCommandIssued

_TOKEN_HASH_KEY = "agent_token_hash"
# Must exceed the agent's longest single command runtime (core upgrade, up to
# _UPGRADE_TIMEOUT=900s in xlink-agent.py). If the lease expires mid-upgrade the
# panel frees the command, re-leases it to the next poll, and the original
# result POST is rejected as a stale lease → the SAME upgrade runs twice.
_LEASE_SECONDS = 960


class CommandService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        signer: CommandSigner,
        events: EventBus | None = None,
        lease_seconds: int = _LEASE_SECONDS,
    ) -> None:
        self._session = session
        self._repo = NodeCommandRepository(session)
        self._signer = signer
        self._events = events
        self._lease_seconds = lease_seconds

    async def enqueue(
        self,
        node: Node,
        *,
        kind: str,
        payload: dict[str, Any],
        origin: str,
        max_attempts: int = 3,
    ) -> NodeCommand:
        if not is_allowed_kind(kind):
            raise ValidationError(f"command kind '{kind}' is not allowed", code="command_kind")
        command_kind = CommandKind(kind)
        try:
            validate_payload(command_kind, payload)
        except CommandValidationError as exc:
            raise ValidationError(str(exc), code="command_payload") from exc

        token_hash = self._token_hash(node)
        command_id = uuid.uuid4()
        signature = self._signer.sign(
            command_id, node.id, kind, payload, node_token_hash=token_hash
        )
        command = NodeCommand(
            id=command_id,
            node_id=node.id,
            kind=command_kind,
            status=CommandStatus.PENDING,
            payload=dict(payload),
            signature=signature,
            origin=origin,
            max_attempts=max_attempts,
        )
        saved = await self._repo.add(command)
        if self._events is not None:
            await self._events.publish(
                NodeCommandIssued(command_id=saved.id, node_id=node.id, kind=kind, origin=origin)
            )
        return saved

    async def enqueue_unique(
        self,
        node: Node,
        *,
        kind: str,
        payload: dict[str, Any],
        origin: str,
        max_attempts: int = 3,
    ) -> NodeCommand | None:
        if await self._repo.has_open_kind(node.id, CommandKind(kind)):
            return None
        return await self.enqueue(
            node, kind=kind, payload=payload, origin=origin, max_attempts=max_attempts
        )

    async def lease(self, node: Node, *, limit: int = 10) -> tuple[str, list[NodeCommand]]:
        now = datetime.now(UTC)
        node_id = node.id
        await self._repo.expire_leases(now)
        self._session.expire_all()
        lease_token = secrets.token_hex(16)
        commands = await self._repo.lease(
            node_id,
            lease_token=lease_token,
            leased_at=now,
            lease_expires_at=now + timedelta(seconds=self._lease_seconds),
            limit=limit,
        )
        return lease_token, list(commands)

    async def report_result(
        self,
        command_id: uuid.UUID,
        *,
        node_id: uuid.UUID,
        lease_token: str,
        success: bool,
        result: dict[str, Any],
    ) -> NodeCommand:
        command = await self._repo.get(command_id)
        if command is None:
            raise NotFoundError("Command not found.", code="command_not_found")
        # A node may only report results for its OWN commands — never another
        # node's, even if it somehow learns the lease token.
        if command.node_id != node_id:
            raise NotFoundError("Command not found.", code="command_not_found")
        if command.lease_token != lease_token:
            raise ValidationError("Invalid or expired lease token.", code="command_lease")
        return await self._repo.complete(
            command, success=success, result=result, completed_at=datetime.now(UTC)
        )

    async def flush(self) -> None:
        await self._session.flush()

    def _token_hash(self, node: Node) -> str:
        token_hash = node.node_metadata.get(_TOKEN_HASH_KEY)
        if not isinstance(token_hash, str) or not token_hash:
            raise ValidationError("Node agent token is not configured.", code="node_token_missing")
        return token_hash
