from __future__ import annotations

import asyncio
import os

import pytest

from app.core.config import Settings
from app.core.exceptions import ConflictError
from app.db.base import Base
from app.db.session import Database
from app.domain.node import Node, NodeStatus
from app.repositories.node import NodeRepository
from app.repositories.user import UserRepository
from app.schemas.node import NodeUpdate
from app.schemas.user import UserCreate
from app.services.node_service import NodeService
from app.services.user_service import UserService

PG_URL = os.environ.get("XLINK_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL or not PG_URL.startswith("postgresql"),
    reason="set XLINK_TEST_DATABASE_URL to a PostgreSQL DSN to run concurrency validation",
)


class _NullCache:
    async def get_json(self, *_a, **_k):
        return None

    async def set_json(self, *_a, **_k):
        return None

    async def delete(self, *_a, **_k):
        return None


async def _make_db() -> Database:
    settings = Settings(
        database_url_override=PG_URL,
        db_pool_size=20,
        db_max_overflow=20,
    )
    db = Database(settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    return db


def _tally(results) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in results:
        out[r] = out.get(r, 0) + 1
    return out


@pytest.mark.parametrize("writers", [50, 100])
async def test_concurrent_distinct_registration(writers: int):
    db = await _make_db()

    async def one(i: int) -> str:
        try:
            async with db.session() as session:
                svc = UserService(UserRepository(session), _NullCache())
                await svc.create(
                    UserCreate(
                        email=f"u{i}@audit.io",
                        username=f"user{i}",
                        password="Str0ng-Passw0rd-123!",
                        full_name="x",
                    )
                )
            return "ok"
        except ConflictError:
            return "conflict"
        except Exception as exc:
            return f"err:{type(exc).__name__}"

    tally = _tally(await asyncio.gather(*[one(i) for i in range(writers)]))
    await db.dispose()
    assert tally.get("ok") == writers
    assert not any(k.startswith("err:") for k in tally)


@pytest.mark.parametrize("writers", [50, 100])
async def test_concurrent_duplicate_registration_exactly_once(writers: int):
    db = await _make_db()

    async def one(_i: int) -> str:
        try:
            async with db.session() as session:
                svc = UserService(UserRepository(session), _NullCache())
                await svc.create(
                    UserCreate(
                        email="dup@audit.io",
                        username="dupuser",
                        password="Str0ng-Passw0rd-123!",
                        full_name="x",
                    )
                )
            return "ok"
        except ConflictError:
            return "conflict"
        except Exception as exc:
            return f"err:{type(exc).__name__}"

    tally = _tally(await asyncio.gather(*[one(i) for i in range(writers)]))
    await db.dispose()
    assert tally.get("ok") == 1
    assert tally.get("conflict") == writers - 1
    assert not any(k.startswith("err:") for k in tally)


@pytest.mark.parametrize("writers", [50, 100])
async def test_concurrent_optimistic_node_update(writers: int):
    db = await _make_db()
    async with db.session() as session:
        node = Node(
            name="hot",
            slug="hot-node",
            host="10.0.0.1",
            port=443,
            max_users=100,
            status=NodeStatus.ACTIVE,
            node_metadata={},
        )
        session.add(node)
        await session.flush()
        node_id = node.id

    async def one(i: int) -> str:
        try:
            async with db.session() as session:
                svc = NodeService(NodeRepository(session))
                await svc.update(node_id, NodeUpdate(max_users=100 + i, expected_version=1))
            return "ok"
        except ConflictError:
            return "conflict"
        except Exception as exc:
            return f"err:{type(exc).__name__}"

    tally = _tally(await asyncio.gather(*[one(i) for i in range(writers)]))
    await db.dispose()
    assert tally.get("ok", 0) >= 1
    assert tally.get("conflict", 0) >= 1
    assert tally.get("ok", 0) + tally.get("conflict", 0) == writers
    assert not any(k.startswith("err:") for k in tally)
