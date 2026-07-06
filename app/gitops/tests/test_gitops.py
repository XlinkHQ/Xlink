from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.session import Database
from app.domain.gitops import GitOpsAction, GitOpsRecord
from app.events.models import NodeOffline
from app.gitops.service import GitOpsService


def test_snapshot_redacts_secrets() -> None:
    service = GitOpsService(session=None)

    snapshot = service.snapshot(
        entity_type="node",
        entity_id=uuid.uuid4(),
        payload={"name": "n1", "api_secret": "super-secret", "nested": {"token": "abc"}},
    )

    assert snapshot.data["api_secret"] == "<redacted>"
    assert snapshot.data["nested"]["token"] == "<redacted>"


def test_diff_generation() -> None:
    service = GitOpsService(session=None)
    entity_id = uuid.uuid4()
    before = service.snapshot(entity_type="node", entity_id=entity_id, payload={"a": 1, "b": 2})
    after = service.snapshot(entity_type="node", entity_id=entity_id, payload={"a": 1, "c": 3})

    diff = service.diff(before, after)

    assert diff.added == {"c": 3}
    assert diff.removed == {"b": 2}
    assert diff.changed == {}


async def test_commit_record_stored(db: Database) -> None:
    async with db.session() as session:
        service = GitOpsService(session)
        after = service.snapshot(entity_type="profile", entity_id=uuid.uuid4(), payload={"v": 1})

        record = await service.commit(before=None, after=after, actor="test", message="init")

        stored = await session.get(GitOpsRecord, record.id)
        assert stored is not None
        assert stored.action is GitOpsAction.COMMIT
        assert stored.diff["added"] == {"v": 1}


async def test_rollback_plan(db: Database) -> None:
    async with db.session() as session:
        service = GitOpsService(session)
        entity_id = uuid.uuid4()
        original = service.snapshot(entity_type="node", entity_id=entity_id, payload={"v": 1})
        changed = service.snapshot(entity_type="node", entity_id=entity_id, payload={"v": 2})
        record = await service.commit(before=None, after=original)

        plan = await service.rollback_plan(record=record, current=changed)

        assert plan.restore_to == {"v": 1}
        assert plan.reverse_diff.changed["v"]["after"] == 1


async def test_event_driven_snapshot(db: Database) -> None:
    async with db.session() as session:
        service = GitOpsService(session)
        event = NodeOffline(node_id=uuid.uuid4(), reason="healthcheck")

        record = await service.snapshot_event(event)
        rows = (await session.execute(select(GitOpsRecord))).scalars().all()

        assert record.action is GitOpsAction.SNAPSHOT
        assert len(rows) == 1
        assert rows[0].entity_type == "NodeOffline"
