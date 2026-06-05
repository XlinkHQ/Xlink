from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Any

import orjson

from app.agent.domain import CommandKind

_ALLOWED_KINDS = frozenset(k.value for k in CommandKind)

_REQUIRED_PAYLOAD: dict[CommandKind, frozenset[str]] = {
    CommandKind.APPLY_CONFIG: frozenset({"config_version"}),
    CommandKind.UPGRADE: frozenset({"target_version"}),
    CommandKind.ROLLBACK: frozenset({"target_version"}),
    CommandKind.RELOAD: frozenset(),
    CommandKind.RESTART: frozenset(),
    CommandKind.COLLECT_DIAGNOSTICS: frozenset(),
    CommandKind.PROVIDER_HEALTHCHECK: frozenset(),
}


class CommandValidationError(ValueError):
    pass


def is_allowed_kind(kind: str) -> bool:
    return kind in _ALLOWED_KINDS


def validate_payload(kind: CommandKind, payload: dict[str, Any]) -> None:
    required = _REQUIRED_PAYLOAD.get(kind, frozenset())
    missing = required - set(payload)
    if missing:
        raise CommandValidationError(
            f"command {kind.value} missing payload fields: {sorted(missing)}"
        )


def _canonical(
    command_id: uuid.UUID, node_id: uuid.UUID, kind: str, payload: dict[str, Any]
) -> bytes:
    body = {
        "command_id": str(command_id),
        "node_id": str(node_id),
        "kind": kind,
        "payload": payload,
    }
    return orjson.dumps(body, option=orjson.OPT_SORT_KEYS)


class CommandSigner:
    def __init__(self, secret: str) -> None:
        self._secret = secret.encode("utf-8")

    def sign(
        self,
        command_id: uuid.UUID,
        node_id: uuid.UUID,
        kind: str,
        payload: dict[str, Any],
        *,
        node_token_hash: str,
    ) -> str:
        key = hmac.new(self._secret, node_token_hash.encode("utf-8"), hashlib.sha256).digest()
        message = _canonical(command_id, node_id, kind, payload)
        return hmac.new(key, message, hashlib.sha256).hexdigest()

    def verify(
        self,
        command_id: uuid.UUID,
        node_id: uuid.UUID,
        kind: str,
        payload: dict[str, Any],
        signature: str,
        *,
        node_token_hash: str,
    ) -> bool:
        expected = self.sign(command_id, node_id, kind, payload, node_token_hash=node_token_hash)
        return hmac.compare_digest(expected, signature)
