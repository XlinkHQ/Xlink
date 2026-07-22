from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.backup.models import BackupScope
from app.backup.service import BackupService
from app.core.exceptions import ValidationError
from app.core.security import hash_password
from app.db.session import Database
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.providers.base.models import ProviderKind


async def _seed(db: Database) -> dict[str, uuid.UUID]:
    async with db.session() as session:
        user = User(
            email="backup@example.com",
            username="backup",
            hashed_password=hash_password("strong-password-123456"),
            role=UserRole.USER,
        )
        node = Node(
            name="node",
            slug=f"node-{uuid.uuid4().hex[:8]}",
            host="node",
            port=443,
            status=NodeStatus.ACTIVE,
            max_users=10,
            current_users=1,
            node_metadata={"assignment_stats": {"a": {"used_bytes": 10}}},
        )
        session.add_all([user, node])
        await session.flush()
        profile = Profile(
            name="profile",
            slug=f"profile-{uuid.uuid4().hex[:8]}",
            provider_kind=ProviderKind.XRAY,
            node_id=node.id,
            protocol="vless",
            settings={},
            is_active=True,
        )
        session.add(profile)
        await session.flush()
        assignment = ClientAssignment(
            user_id=user.id,
            profile_id=profile.id,
            node_id=node.id,
            provider_kind=ProviderKind.XRAY,
            status=AssignmentStatus.ACTIVE,
        )
        session.add(assignment)
        await session.flush()
        return {
            "user": user.id,
            "node": node.id,
            "profile": profile.id,
            "assignment": assignment.id,
        }


async def _service_export_full(db: Database):
    async with db.sessionmaker() as session:
        return await BackupService(session).export_full()


async def _service_export_incremental(db: Database, since: datetime):
    async with db.sessionmaker() as session:
        return await BackupService(session).export_incremental(since=since)


async def _service_restore(db: Database, document, *, dry_run: bool):
    async with db.sessionmaker() as session:
        return await BackupService(session).restore(document, dry_run=dry_run)


async def test_full_export_and_secret_redaction(db: Database) -> None:
    await _seed(db)
    backup = await _service_export_full(db)

    assert backup.scope is BackupScope.FULL
    assert backup.checksum
    assert len(backup.data["users"]) == 1
    assert backup.data["users"][0]["hashed_password"] == "<redacted>"
    assert backup.data["traffic_metadata"]


async def test_incremental_export(db: Database) -> None:
    await _seed(db)
    since = datetime.now(UTC) + timedelta(days=1)

    backup = await _service_export_incremental(db, since)

    assert backup.scope is BackupScope.INCREMENTAL
    assert backup.data["users"] == []


async def test_restore_validation_and_dry_run(db: Database) -> None:
    await _seed(db)
    document = await _service_export_full(db)
    payload = dataclasses.asdict(document)

    result = await _service_restore(db, payload, dry_run=True)

    assert result.dry_run is True
    assert result.users == 1


async def test_restore_persists_data(db: Database) -> None:
    await _seed(db)
    document = await _service_export_full(db)
    payload = dataclasses.asdict(document)

    async with db.session() as session:
        result = await BackupService(session).restore(payload, dry_run=False)
        assert result.dry_run is False
        assert result.users == 1
        restored_user = await session.get(User, payload["data"]["users"][0]["id"])
        assert restored_user is not None


async def test_corrupted_backup_rejected(db: Database) -> None:
    await _seed(db)
    document = dataclasses.asdict(await _service_export_full(db))
    document["data"]["users"] = []

    with pytest.raises(ValidationError) as exc_info:
        await _service_restore(db, document, dry_run=True)

    assert exc_info.value.code == "backup_corrupted"


async def test_missing_dependency_rejected(db: Database) -> None:
    await _seed(db)
    document = dataclasses.asdict(await _service_export_full(db))

    document["data"]["nodes"] = []
    orphan_node = str(uuid.uuid4())
    for profile in document["data"]["profiles"]:
        profile["node_id"] = orphan_node
    # Re-checksum the mutated data so it passes the integrity gate and the FK
    # dependency check is what actually rejects it (a null checksum is now
    # rejected earlier, so leaving it null would test the wrong guard).
    from app.backup.validator import checksum_payload

    document["checksum"] = checksum_payload(document["data"])

    with pytest.raises(ValidationError) as exc_info:
        await _service_restore(db, document, dry_run=True)

    assert exc_info.value.code == "backup_missing_dependency"
