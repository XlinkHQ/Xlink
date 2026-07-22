from __future__ import annotations

import asyncio
import contextlib

from app.core.cache import CacheProtocol
from app.core.leader import LeaderElector
from app.core.logging import get_logger
from app.db.session import Database
from app.repositories.certificate import CertificateRepository
from app.services.certificate_service import CertificateService

logger = get_logger("xlink.services.cert_renewal")


class CertRenewalJob:
    def __init__(
        self,
        db: Database,
        cache: CacheProtocol,
        *,
        email: str,
        interval_seconds: int,
        window_days: int,
        staging: bool = False,
        leader: LeaderElector | None = None,
    ) -> None:
        self._db = db
        self._cache = cache
        self._email = email
        self._interval = interval_seconds
        self._window_days = window_days
        self._staging = staging
        self._leader = leader
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="cert-renewal")
        logger.info("cert_renewal_started", interval_seconds=self._interval)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
        logger.info("cert_renewal_stopped")

    async def _run(self) -> None:
        while not self._stopping.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            if self._stopping.is_set():
                break
            if self._leader is not None and not self._leader.is_leader:
                continue
            try:
                await self.renew_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("cert_renewal_failed")

    async def renew_once(self) -> int:
        async with self._db.session() as session:
            service = CertificateService(CertificateRepository(session))
            renewed = await service.renew_due(
                self._cache,
                email=self._email,
                staging=self._staging,
                window_days=self._window_days,
            )
        if renewed:
            logger.info("cert_renewal_renewed", count=renewed)
        return renewed
