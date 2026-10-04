from __future__ import annotations

import asyncio
import secrets

from app.providers.base.exceptions import ClientAlreadyExistsError, ClientNotFoundError
from app.providers.base.models import (
    ClientResult,
    ClientSpec,
    ProviderCapability,
    ProviderKind,
    ProviderMetadata,
)
from app.providers.base.provider import Provider
from app.providers.base.store import JsonClientStore

PROVIDER_NAME = "hysteria"

_CAPABILITIES = frozenset(
    {
        ProviderCapability.CREATE_CLIENT,
        ProviderCapability.UPDATE_CLIENT,
        ProviderCapability.DELETE_CLIENT,
        ProviderCapability.GET_CLIENT,
    }
)


class HysteriaProvider(Provider):
    def __init__(self, *, data_dir: str | None = None) -> None:
        self._clients = JsonClientStore(PROVIDER_NAME, data_dir=data_dir)

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name=PROVIDER_NAME,
            kind=ProviderKind.HYSTERIA,
            capabilities=_CAPABILITIES,
        )

    def _create_client_sync(self, spec: ClientSpec) -> ClientResult:
        self.ensure_capability(ProviderCapability.CREATE_CLIENT)
        if spec.client_id in self._clients:
            raise ClientAlreadyExistsError(details={"client_id": spec.client_id})
        return self._store(spec)

    def _update_client_sync(self, spec: ClientSpec) -> ClientResult:
        self.ensure_capability(ProviderCapability.UPDATE_CLIENT)
        if spec.client_id not in self._clients:
            return self._store(spec)
        existing = self._clients[spec.client_id]
        return self._store(spec, existing=existing)

    def _delete_client_sync(self, client_id: str) -> None:
        self.ensure_capability(ProviderCapability.DELETE_CLIENT)
        if self._clients.pop(client_id, None) is None:
            raise ClientNotFoundError(details={"client_id": client_id})

    def _get_client_sync(self, client_id: str) -> ClientResult:
        self.ensure_capability(ProviderCapability.GET_CLIENT)
        record = self._clients.get(client_id)
        if record is None:
            raise ClientNotFoundError(details={"client_id": client_id})
        return ClientResult(client_id=client_id, provider=PROVIDER_NAME, raw=dict(record))

    # The client store is a JSON file guarded by an exclusive flock and
    # rewritten (with fsync) on every change, so each call is O(clients) of
    # blocking I/O. Run it off the event loop: at 20k clients one create
    # held the loop ~160 ms, stalling every other request, and flock
    # contention between gunicorn workers could hold it far longer.
    async def create_client(self, spec: ClientSpec) -> ClientResult:
        return await asyncio.to_thread(self._create_client_sync, spec)

    async def update_client(self, spec: ClientSpec) -> ClientResult:
        return await asyncio.to_thread(self._update_client_sync, spec)

    async def delete_client(self, client_id: str) -> None:
        return await asyncio.to_thread(self._delete_client_sync, client_id)

    async def get_client(self, client_id: str) -> ClientResult:
        return await asyncio.to_thread(self._get_client_sync, client_id)

    async def health_check(self) -> bool:
        try:
            return self._clients.exists()
        except Exception:
            return False

    def _store(
        self,
        spec: ClientSpec,
        existing: dict[str, str] | None = None,
    ) -> ClientResult:
        if existing is not None:
            record: dict[str, str] = {"password": existing["password"]}
            if "obfs_password" in existing:
                record["obfs_password"] = existing["obfs_password"]
            elif spec.attributes.get("obfs"):
                record["obfs_password"] = secrets.token_urlsafe(16)
        else:
            record = {"password": secrets.token_urlsafe(24)}
            if spec.attributes.get("obfs"):
                record["obfs_password"] = secrets.token_urlsafe(16)

        self._clients[spec.client_id] = record
        return ClientResult(client_id=spec.client_id, provider=PROVIDER_NAME, raw=dict(record))
