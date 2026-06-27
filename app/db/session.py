from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        is_sqlite = settings.database_url.startswith("sqlite")

        engine_kwargs: dict[str, object] = {}
        if not is_sqlite:
            if settings.db_uses_pgbouncer:
                engine_kwargs = {
                    "poolclass": NullPool,
                    "connect_args": {"statement_cache_size": 0},
                }
            else:
                engine_kwargs = {
                    "pool_size": settings.db_pool_size,
                    "max_overflow": settings.db_max_overflow,
                    "pool_timeout": settings.db_pool_timeout,
                    "pool_recycle": settings.db_pool_recycle,
                    "pool_pre_ping": settings.db_pool_pre_ping,
                }

        self._engine: AsyncEngine = create_async_engine(
            settings.database_url,
            echo=settings.db_echo,
            future=True,
            **engine_kwargs,
        )
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        return self._sessionmaker

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        session = self._sessionmaker()
        try:
            yield session
            await session.commit()
        except Exception as exc:
            try:
                await session.rollback()
            except Exception as rollback_exc:
                raise rollback_exc from exc
            raise
        finally:
            await session.close()

    def pool_stats(self) -> dict[str, int | str]:
        pool = self._engine.pool
        stats: dict[str, int | str] = {"pool_class": type(pool).__name__}
        for attr in ("size", "checkedin", "checkedout", "overflow"):
            getter = getattr(pool, attr, None)
            if callable(getter):
                try:
                    stats[attr] = int(getter())
                except (TypeError, ValueError):
                    continue
        stats["mode"] = self._settings.db_pool_mode
        stats["max_total_connections"] = self._settings.db_max_total_connections
        return stats

    async def dispose(self) -> None:
        await self._engine.dispose()
