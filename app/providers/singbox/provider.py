from __future__ import annotations

import asyncio
import secrets
import uuid

from app.providers.base import ss2022
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

PROVIDER_NAME = "sing-box"

_CAPABILITIES = frozenset(
    {
        ProviderCapability.CREATE_CLIENT,
        ProviderCapability.UPDATE_CLIENT,
        ProviderCapability.DELETE_CLIENT,
        ProviderCapability.GET_CLIENT,
    }
)

_PASSWORD_PROTOCOLS = frozenset(
    {
        "trojan",
        "shadowsocks",
        "shadowsocks2022",
        "shadowtls",
        "hysteria2",
        "tuic",
        "naive",
        "anytls",
    }
)

def _gen_password(protocol: str, settings: dict | None) -> str:
    method = str((settings or {}).get("method", "")).strip().lower()
    if protocol == "shadowsocks2022" or ss2022.is_2022(method):
        return ss2022.new_key(method or ss2022.DEFAULT_METHOD)
    return secrets.token_urlsafe(24)


class SingBoxProvider(Provider):
    def __init__(self, *, data_dir: str | None = None) -> None:
        self._clients = JsonClientStore(PROVIDER_NAME, data_dir=data_dir)

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name=PROVIDER_NAME,
            kind=ProviderKind.SING_BOX,
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
            raise ClientNotFoundError(details={"client_id": spec.client_id})
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
        protocol = str(spec.attributes.get("protocol", "vless")).strip().lower()
        settings = spec.attributes.get("settings")
        settings = settings if isinstance(settings, dict) else {}

        if existing is not None:
            record: dict[str, str] = {
                "uuid": existing.get("uuid") or str(uuid.uuid4()),
                "protocol": protocol,
            }
            if protocol in _PASSWORD_PROTOCOLS:
                record["password"] = (
                    existing["password"]
                    if "password" in existing
                    else _gen_password(protocol, settings)
                )
        else:
            record = {"uuid": str(uuid.uuid4()), "protocol": protocol}
            if protocol in _PASSWORD_PROTOCOLS:
                record["password"] = _gen_password(protocol, settings)

        for key, value in settings.items():
            record[str(key)] = str(value)
        self._clients[spec.client_id] = record
        return ClientResult(client_id=spec.client_id, provider=PROVIDER_NAME, raw=dict(record))
