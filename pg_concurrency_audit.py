from __future__ import annotations

import asyncio
import os
import uuid

os.environ["XLINK_ENV"] = "testing"
os.environ["XLINK_JWT_SECRET_KEY"] = "audit-secret-key-32-chars-minimum-9xZ"
os.environ.setdefault("XLINK_ARGON2_TIME_COST", "1")
os.environ.setdefault("XLINK_ARGON2_MEMORY_COST", "8192")
os.environ.setdefault("XLINK_ARGON2_PARALLELISM", "1")

from app.core.config import Settings
from app.core.exceptions import ConflictError
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import Database
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.repositories.node import NodeRepository
from app.repositories.user import UserRepository
from app.schemas.node import NodeUpdate
from app.schemas.user import UserCreate
from app.services.node_service import NodeService
from app.services.user_service import UserService

PG_URL = os.environ.get(
    "XLINK_TEST_DATABASE_URL",
    "postgresql+asyncpg://audit:auditpass@localhost:55432/auditdb",
)


def make_db(pool_size: int) -> Database:
    settings = Settings(
        database_url_override=PG_URL,
        db_pool_size=pool_size,
        db_max_overflow=pool_size,
    )
    return Database(settings)


async def reset(db: Database) -> None:
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def concurrent_registration(db: Database, n: int) -> dict:
    async def one(i: int):
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

    results = await asyncio.gather(*[one(i) for i in range(n)])
    return _tally(results)


async def concurrent_duplicate_registration(db: Database, n: int) -> dict:
    async def one(_i: int):
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

    results = await asyncio.gather(*[one(i) for i in range(n)])
    return _tally(results)


async def concurrent_node_updates(db: Database, n: int) -> dict:
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

    async def one(i: int):
        try:
            async with db.session() as session:
                svc = NodeService(NodeRepository(session))
                await svc.update(node_id, NodeUpdate(max_users=100 + i, expected_version=1))
            return "ok"
        except ConflictError:
            return "conflict"
        except Exception as exc:
            return f"err:{type(exc).__name__}"

    results = await asyncio.gather(*[one(i) for i in range(n)])
    return _tally(results)


def _tally(results) -> dict:
    out: dict[str, int] = {}
    for r in results:
        out[r] = out.get(r, 0) + 1
    return out


class _NullCache:
    async def get_json(self, *_a, **_k):
        return None

    async def set_json(self, *_a, **_k):
        return None

    async def delete(self, *_a, **_k):
        return None


async def main():
    print("=" * 70)
    print("POSTGRESQL CONCURRENCY VALIDATION")
    print(f"target: {PG_URL}")
    print("=" * 70)
    for writers in (50, 100):
        db = make_db(pool_size=20)
        await reset(db)
        reg = await concurrent_registration(db, writers)
        print(f"[{writers}w] distinct registration : {reg}")
        await reset(db)
        dup = await concurrent_duplicate_registration(db, writers)
        print(f"[{writers}w] duplicate registration: {dup}")
        await reset(db)
        upd = await concurrent_node_updates(db, writers)
        print(f"[{writers}w] optimistic node update: {upd}")
        await db.dispose()
    print("\nVALIDATION COMPLETE")


if __name__ == "__main__":
    asyncio.run(main())
