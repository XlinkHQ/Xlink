from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.inbound_host import InboundHost


class InboundHostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, host_id: uuid.UUID) -> InboundHost | None:
        return await self.session.get(InboundHost, host_id)

    async def list_for_profile(self, profile_id: uuid.UUID) -> Sequence[InboundHost]:
        stmt = (
            select(InboundHost)
            .where(InboundHost.profile_id == profile_id)
            .order_by(InboundHost.weight.desc(), InboundHost.created_at.asc())
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def list_all(self) -> Sequence[InboundHost]:
        stmt = select(InboundHost).order_by(InboundHost.weight.desc(), InboundHost.created_at.asc())
        return (await self.session.execute(stmt)).scalars().all()

    async def add(self, host: InboundHost) -> InboundHost:
        self.session.add(host)
        await self.session.flush()
        return host

    async def delete(self, host: InboundHost) -> None:
        await self.session.delete(host)
        await self.session.flush()

    async def overrides_for_profiles(
        self, profile_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict[str, Any]]]:
        if not profile_ids:
            return {}
        stmt = (
            select(InboundHost)
            .where(
                InboundHost.is_disabled.is_(False),
                or_(
                    InboundHost.profile_id.in_(list(profile_ids)),
                    InboundHost.is_universal.is_(True),
                ),
            )
            .order_by(InboundHost.weight.desc(), InboundHost.created_at.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        if not rows:
            return {}

        universal: list[dict[str, Any]] = []
        by_profile: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for h in rows:
            ov = h.to_override()
            if h.is_universal:
                universal.append(ov)
            else:
                by_profile.setdefault(h.profile_id, []).append(ov)
        result: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for pid in profile_ids:
            hosts = by_profile.get(pid, []) + universal
            if hosts:
                result[pid] = hosts
        return result
