from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.core.exceptions import NotFoundError, ValidationError
from app.domain.inbound_host import InboundHost
from app.repositories.inbound_host import InboundHostRepository
from app.schemas.inbound_host import InboundHostCreate, InboundHostUpdate, validate_asn_addresses


class InboundHostService:
    def __init__(self, repo: InboundHostRepository, subscription_service=None) -> None:  # noqa: ANN001
        self._repo = repo
        # Hosts are rendered straight into feeds; without invalidation an edited
        # address or SNI kept being served from cache until the TTL ran out.
        self._subscriptions = subscription_service

    async def _changed(self) -> None:
        if self._subscriptions is not None:
            await self._subscriptions.invalidate_cache()

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
            asn_addresses=validate_asn_addresses(data.asn_addresses),
        )
        saved = await self._repo.add(host)
        await self._changed()
        return saved

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
        if "asn_addresses" in data.model_fields_set:
            host.asn_addresses = validate_asn_addresses(data.asn_addresses)
        await self._repo.add(host)
        await self._changed()
        return host

    async def delete(self, host_id: uuid.UUID) -> None:
        host = await self.get(host_id)
        await self._repo.delete(host)
        await self._changed()
