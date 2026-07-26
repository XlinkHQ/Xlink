from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from pydantic_core import to_jsonable_python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.domain.node import Node
from app.domain.profile import Profile
from app.domain.user import User

logger = logging.getLogger(__name__)


_CANONICAL_SEPARATORS = (",", ":")


def canonical_row(row: dict[str, Any]) -> str:
    """Canonical JSON for a single row: sorted keys, compact separators. Feeding
    the concatenation of these (with array/object punctuation) to sha256 yields
    the exact same digest as ``checksum_payload`` over the whole document."""
    return json.dumps(to_jsonable_python(row), sort_keys=True, separators=_CANONICAL_SEPARATORS)


def checksum_payload(data: dict[str, list[dict[str, Any]]]) -> str:
    normalized = to_jsonable_python(data)
    raw = json.dumps(normalized, sort_keys=True, separators=_CANONICAL_SEPARATORS)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class BackupValidator:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self._session = session

    async def validate(self, document: dict[str, Any]) -> None:
        if document.get("schema_version") != 1:
            raise ValidationError("Unsupported backup schema.", code="backup_schema_unsupported")
        data = document.get("data")
        if not isinstance(data, dict):
            raise ValidationError("Backup data is corrupted.", code="backup_corrupted")
        checksum = document.get("checksum")
        if checksum is None:
            raise ValidationError(
                "Backup document has no checksum — integrity cannot be verified.",
                code="backup_checksum_missing",
            )
        if checksum != checksum_payload(data):
            raise ValidationError("Backup checksum mismatch.", code="backup_corrupted")
        await self._validate_foreign_keys(data)

    async def _validate_foreign_keys(self, data: dict[str, list[dict[str, Any]]]) -> None:
        user_ids = {row["id"] for row in data.get("users", []) if "id" in row}
        node_ids = {row["id"] for row in data.get("nodes", []) if "id" in row}
        profile_ids = {row["id"] for row in data.get("profiles", []) if "id" in row}

        if self._session is not None:
            for model, id_set in (
                (User, user_ids),
                (Node, node_ids),
                (Profile, profile_ids),
            ):
                stmt = select(model.id)
                rows = (await self._session.execute(stmt)).scalars().all()
                id_set.update(rows)

        for profile in data.get("profiles", []):
            if profile.get("node_id") not in node_ids:
                raise ValidationError(
                    "Profile references missing node.",
                    code="backup_missing_dependency",
                )
        for assignment in data.get("assignments", []):
            if assignment.get("user_id") not in user_ids:
                raise ValidationError(
                    "Assignment references missing user.",
                    code="backup_missing_dependency",
                )
            if assignment.get("node_id") not in node_ids:
                raise ValidationError(
                    "Assignment references missing node.",
                    code="backup_missing_dependency",
                )
            if assignment.get("profile_id") not in profile_ids:
                raise ValidationError(
                    "Assignment references missing profile.",
                    code="backup_missing_dependency",
                )
