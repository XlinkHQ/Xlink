from __future__ import annotations

import hashlib
import json
from typing import Any

from app.core.exceptions import ValidationError


def checksum_payload(data: dict[str, list[dict[str, Any]]]) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class BackupValidator:
    def validate(self, document: dict[str, Any]) -> None:
        if document.get("schema_version") != 1:
            raise ValidationError("Unsupported backup schema.", code="backup_schema_unsupported")
        data = document.get("data")
        if not isinstance(data, dict):
            raise ValidationError("Backup data is corrupted.", code="backup_corrupted")
        checksum = document.get("checksum")
        if checksum is not None and checksum != checksum_payload(data):
            raise ValidationError("Backup checksum mismatch.", code="backup_corrupted")
        self._validate_foreign_keys(data)

    def _validate_foreign_keys(self, data: dict[str, list[dict[str, Any]]]) -> None:
        user_ids = {row["id"] for row in data.get("users", []) if "id" in row}
        node_ids = {row["id"] for row in data.get("nodes", []) if "id" in row}
        profile_ids = {row["id"] for row in data.get("profiles", []) if "id" in row}
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
