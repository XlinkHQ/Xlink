from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.backup.schemas import RestoreResult
from app.backup.validator import BackupValidator
from app.domain.client_assignment import ClientAssignment
from app.domain.node import Node
from app.domain.profile import Profile
from app.domain.user import User


class BackupImporter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._validator = BackupValidator()

    async def restore(self, document: dict[str, Any], *, dry_run: bool = False) -> RestoreResult:
        self._validator.validate(document)
        data = document["data"]
        counts = {
            "users": len(data.get("users", [])),
            "nodes": len(data.get("nodes", [])),
            "profiles": len(data.get("profiles", [])),
            "assignments": len(data.get("assignments", [])),
        }
        if dry_run:
            return RestoreResult(dry_run=True, **counts)
        for model, key in (
            (User, "users"),
            (Node, "nodes"),
            (Profile, "profiles"),
            (ClientAssignment, "assignments"),
        ):
            for row in data.get(key, []):
                await self._upsert(model, row)
        await self._session.flush()
        return RestoreResult(dry_run=False, **counts)

    async def _upsert(self, model, row: dict[str, Any]) -> None:
        values = dict(row)
        if model is Node and "metadata" in values:
            values["node_metadata"] = values.pop("metadata")
        instance = await self._session.get(model, values["id"])
        if instance is None:
            if model is User and values.get("hashed_password") == "<redacted>":
                values["hashed_password"] = "restored-redacted-password"
            self._session.add(model(**values))
            return
        for key, value in values.items():
            if key == "id":
                continue
            if model is User and key == "hashed_password" and value == "<redacted>":
                continue
            setattr(instance, key, value)
