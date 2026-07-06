from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from app.gitops.models import GitSnapshot

_REDACTED = "<redacted>"
_SENSITIVE_FRAGMENTS = (
    "password",
    "secret",
    "token",
    "credential",
    "private_key",
    "api_key",
    "apikey",
    "access_key",
    "secret_key",
    "auth_key",
    "signing_key",
    "ssh_key",
)


class SnapshotBuilder:
    def capture(
        self,
        *,
        entity_type: str,
        entity_id,
        payload: Mapping[str, Any],
    ) -> GitSnapshot:
        return GitSnapshot(
            entity_type=entity_type,
            entity_id=entity_id,
            data=_redact(_normalize(dict(payload))),
        )


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | UUID):
        return str(value)
    return value


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted = {}
        for key, item in value.items():
            redacted[key] = _REDACTED if _is_sensitive(key) else _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _is_sensitive(key: str) -> bool:
    lower_key = key.lower()
    return any(fragment in lower_key for fragment in _SENSITIVE_FRAGMENTS)
