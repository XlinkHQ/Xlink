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
from app.core.logging import get_logger

logger = get_logger("xlink.db")


class Database:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

        self._engine: AsyncEngine = self._build_engine(settings.database_url)
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        # OPTIONAL read-replica. Built ONLY when a replica URL is configured; with
        # no replica set, _reader_engine/_reader_sessionmaker stay None and every
        # read falls back to the primary — behaviour is byte-for-byte the single
        # engine as before.
        self._reader_engine: AsyncEngine | None = None
        self._reader_sessionmaker: async_sessionmaker[AsyncSession] | None = None
        replica_url = settings.database_url_replica
        if replica_url:
            self._reader_engine = self._build_engine(replica_url, replica=True)
            self._reader_sessionmaker = async_sessionmaker(
                bind=self._reader_engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
            )
            logger.info("db_read_replica_enabled")

    def _build_engine(self, url: str, *, replica: bool = False) -> AsyncEngine:
        settings = self._settings
        is_sqlite = url.startswith("sqlite")

        engine_kwargs: dict[str, object] = {}
        if not is_sqlite:
            if settings.db_uses_pgbouncer:
                engine_kwargs = {
                    "poolclass": NullPool,
                    "connect_args": {"statement_cache_size": 0},
                }
            else:
                pool_size = settings.db_pool_size
                max_overflow = settings.db_max_overflow
                if replica:
                    if settings.db_replica_pool_size is not None:
                        pool_size = settings.db_replica_pool_size
                    if settings.db_replica_max_overflow is not None:
                        max_overflow = settings.db_replica_max_overflow
                engine_kwargs = {
                    "pool_size": pool_size,
                    "max_overflow": max_overflow,
                    "pool_timeout": settings.db_pool_timeout,
                    "pool_recycle": settings.db_pool_recycle,
                    "pool_pre_ping": settings.db_pool_pre_ping,
                }

        return create_async_engine(
            url,
            echo=settings.db_echo,
            future=True,
            **engine_kwargs,
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        return self._sessionmaker

    @property
    def has_replica(self) -> bool:
        """True only when a distinct read-replica engine was built."""
        return self._reader_sessionmaker is not None

    @property
    def reader_engine(self) -> AsyncEngine | None:
        """The replica engine, or None when no replica is configured."""
        return self._reader_engine

    @property
    def reader_sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        """The replica sessionmaker when a replica is configured, otherwise the
        PRIMARY sessionmaker — callers can always use it and get correct results
        whether or not a replica exists."""
        return self._reader_sessionmaker or self._sessionmaker

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

    @asynccontextmanager
    async def reader_session(self) -> AsyncIterator[AsyncSession]:
        """Read-only session for analytics/subscription reads that tolerate
        replica lag (NOT read-your-writes).

        - No replica configured → yields a PRIMARY session, so behaviour is
          identical to a normal read today.
        - Replica configured → yields a replica session. If opening the replica
          session fails for any reason (unreachable standby, pool error) we FAIL
          SAFE by falling back to the primary rather than surfacing a replica
          outage as a read failure — a read that could have hit the primary must
          not break because the replica is down.

        The session is never committed (reads only) and is rolled back on the way
        out so a replica connection is never left holding an idle transaction.
        """
        maker = self.reader_sessionmaker
        try:
            session = maker()
        except Exception:
            if maker is self._sessionmaker:
                raise
            logger.warning("db_reader_session_open_failed_fallback_primary", exc_info=True)
            session = self._sessionmaker()
        try:
            yield session
        finally:
            try:
                await session.rollback()
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
        if self._reader_engine is not None:
            await self._reader_engine.dispose()
