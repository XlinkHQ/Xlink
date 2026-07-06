from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.core.exceptions import NotFoundError, ValidationError
from app.domain.inbound_host import InboundHost
from app.repositories.inbound_host import InboundHostRepository
from app.schemas.inbound_host import InboundHostCreate, InboundHostUpdate


class InboundHostService:
    def __init__(self, repo: InboundHostRepository) -> None:
        self._repo = repo

    async def list(self, profile_id: uuid.UUID | None = None) -> Sequence[InboundHost]:
        if profile_id is not None:
            return await self._repo.list_for_profile(profile_id)
        return await self._repo.list_all()

    async def get(self, host_id: uuid.UUID) -> InboundHost:
        host = await self._repo.get(host_id)
        if host is None:
            raise NotFoundError("Inbound host not found.", code="inbound_host_not_found")
        return host

    async def create(self, data: InboundHostCreate) -> InboundHost:
        if data.profile_id is None and not data.is_universal:
            raise ValidationError(
                "A host must belong to an inbound or be marked universal.",
                code="inbound_host_unbound",
            )
        host = InboundHost(
            profile_id=data.profile_id,
            remark=data.remark,
            address=data.address,
            port=data.port,
            sni=data.sni,
            host=data.host,
            path=data.path,
            alpn=data.alpn,
            fingerprint=data.fingerprint,
            security=data.security,
            network=data.network,
            fragment=data.fragment,
            noise=data.noise,
            mux=data.mux,
            allow_insecure=data.allow_insecure,
            weight=data.weight,
            is_universal=data.is_universal,
            is_disabled=data.is_disabled,
            chain_target_id=data.chain_target_id,
        )
        return await self._repo.add(host)

    async def update(self, host_id: uuid.UUID, data: InboundHostUpdate) -> InboundHost:
        host = await self.get(host_id)
        for field in (
            "remark",
            "address",
            "port",
            "sni",
            "host",
            "path",
            "alpn",
            "fingerprint",
            "security",
            "network",
            "fragment",
            "noise",
            "mux",
            "allow_insecure",
            "weight",
            "is_universal",
            "is_disabled",
            "chain_target_id",
        ):
            value = getattr(data, field)
            if value is not None:
                setattr(host, field, value)
        await self._repo.add(host)
        return host

    async def delete(self, host_id: uuid.UUID) -> None:
        host = await self.get(host_id)
        await self._repo.delete(host)
