from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.certificate import Certificate, CertificateSource


class CertificateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[Certificate]:
        stmt = select(Certificate).order_by(Certificate.domain)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_acme_due(self, *, before: datetime) -> list[Certificate]:
        stmt = select(Certificate).where(
            Certificate.source == CertificateSource.ACME,
            or_(Certificate.not_after.is_(None), Certificate.not_after < before),
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get(self, cert_id: uuid.UUID) -> Certificate | None:
        return await self.session.get(Certificate, cert_id)

    async def get_by_domain(self, domain: str) -> Certificate | None:
        stmt = select(Certificate).where(Certificate.domain == domain)
        return (await self.session.execute(stmt)).scalars().first()

    async def add(self, cert: Certificate) -> Certificate:
        self.session.add(cert)
        await self.session.flush()
        return cert

    async def delete(self, cert: Certificate) -> None:
        await self.session.delete(cert)
        await self.session.flush()
