from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.backup.exporter import _REDACTED
from app.backup.schemas import RestoreResult
from app.backup.validator import BackupValidator
from app.core.exceptions import ValidationError
from app.domain.client_assignment import ClientAssignment
from app.domain.node import Node
from app.domain.profile import Profile
from app.domain.user import User

_RESET_REQUIRED_HASH = "!reset-required"


class BackupImporter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._validator = BackupValidator(session=session)

    async def restore(self, document: dict[str, Any], *, dry_run: bool = False) -> RestoreResult:
        await self._validator.validate(document)
        data = document["data"]
        counts = {
            "users": len(data.get("users", [])),
            "nodes": len(data.get("nodes", [])),
            "profiles": len(data.get("profiles", [])),
            "assignments": len(data.get("assignments", [])),
        }
        if dry_run:
            return RestoreResult(dry_run=True, **counts)
        # Users carry a self-referential owner_id FK with no ORM relationship, so
        # SQLAlchemy won't order parent-before-child on flush. Insert owners
        # (owner_id is null) before sub-users, and within sub-users insert an
        # owner before anyone it owns, so a reseller's own row exists before its
        # users reference it — otherwise the FK check aborts the whole restore.
        users = _order_users_by_ownership(data.get("users", []))
        for row in users:
            await self._upsert(User, row)
        for model, key in ((Node, "nodes"), (Profile, "profiles")):
            for row in data.get(key, []):
                await self._upsert(model, row)
        # group_id points at the groups table, which the backup does not export;
        # a grouped assignment restored into a DB lacking that group would raise
        # an FK violation and abort the restore. Groups are optional metadata, so
        # drop a group_id whose group isn't present rather than fail the restore.
        for row in data.get("assignments", []):
            await self._upsert(ClientAssignment, row, drop_missing_group=True)
        await self._session.flush()
        return RestoreResult(dry_run=False, **counts)

    @staticmethod
    def _coerce(model, values: dict[str, Any]) -> dict[str, Any]:
        columns = model.__mapper__.columns
        for key, value in list(values.items()):
            if value is None or not isinstance(value, str):
                continue
            col = columns.get(key)
            if col is None:
                continue
            try:
                py = col.type.python_type
            except (NotImplementedError, AttributeError):
                continue
            try:
                if py is datetime:
                    dt = datetime.fromisoformat(value)
                    values[key] = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
                elif py is uuid.UUID:
                    values[key] = uuid.UUID(value)
                elif py is bool:
                    values[key] = value.strip().lower() in ("true", "1", "yes", "on")
            except (ValueError, TypeError):
                continue
        return values

    async def _upsert(self, model, row: dict[str, Any], *, drop_missing_group: bool = False) -> None:
        values = dict(row)
        if model is Node and "metadata" in values:
            values["node_metadata"] = values.pop("metadata")
        if "id" not in values:
            raise ValidationError("Row missing required id field", code="backup_malformed")
        values = self._coerce(model, values)
        if drop_missing_group and values.get("group_id") is not None:
            from app.domain.group import Group

            if await self._session.get(Group, values["group_id"]) is None:
                values["group_id"] = None
        instance = await self._session.get(model, values["id"])
        if instance is None:
            if model is User and values.get("hashed_password") == _REDACTED:
                values["hashed_password"] = _RESET_REQUIRED_HASH
            if model is User and values.get("totp_secret") == _REDACTED:
                values["totp_secret"] = None
                values["totp_enabled"] = False
            self._session.add(model(**values))
            return
        for key, value in values.items():
            if key == "id":
                continue
            if key == "version":
                continue
            if model is User and key == "hashed_password" and value == _REDACTED:
                continue
            if model is User and key == "totp_secret" and value == _REDACTED:
                continue
            setattr(instance, key, value)


def _order_users_by_ownership(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {r.get("id"): r for r in rows}
    ordered: list[dict[str, Any]] = []
    placed: set = set()

    def place(row: dict[str, Any]) -> None:
        rid = row.get("id")
        if rid in placed:
            return
        owner = row.get("owner_id")
        if owner is not None and owner in by_id and owner not in placed:
            place(by_id[owner])
        placed.add(rid)
        ordered.append(row)

    for r in rows:
        place(r)
    return ordered
