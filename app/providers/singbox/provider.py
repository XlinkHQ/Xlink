from __future__ import annotations

import secrets
import uuid

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
    {"trojan", "shadowsocks", "shadowsocks2022", "shadowtls", "hysteria2", "tuic", "naive"}
)

# Shadowsocks-2022 requires a base64 PSK whose decoded length matches the AEAD
# key size (16B for aes-128, 32B otherwise). A random urlsafe string is rejected
# by the core, so mint a correctly-sized key.
_SS2022_KEY_BYTES = {"2022-blake3-aes-128-gcm": 16}


def _ss2022_password(method: str) -> str:
    import base64

    n = _SS2022_KEY_BYTES.get(method, 32)
    return base64.b64encode(secrets.token_bytes(n)).decode("ascii")


def _gen_password(protocol: str, settings: dict | None) -> str:
    method = str((settings or {}).get("method", "")).strip().lower()
    if protocol == "shadowsocks2022" or method.startswith("2022-"):
        return _ss2022_password(method or "2022-blake3-aes-256-gcm")
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

    async def create_client(self, spec: ClientSpec) -> ClientResult:
        self.ensure_capability(ProviderCapability.CREATE_CLIENT)
        if spec.client_id in self._clients:
            raise ClientAlreadyExistsError(details={"client_id": spec.client_id})
        return self._store(spec)

    async def update_client(self, spec: ClientSpec) -> ClientResult:
        self.ensure_capability(ProviderCapability.UPDATE_CLIENT)
        if spec.client_id not in self._clients:
            raise ClientNotFoundError(details={"client_id": spec.client_id})
        existing = self._clients[spec.client_id]
        return self._store(spec, existing=existing)

    async def delete_client(self, client_id: str) -> None:
        self.ensure_capability(ProviderCapability.DELETE_CLIENT)
        if self._clients.pop(client_id, None) is None:
            raise ClientNotFoundError(details={"client_id": client_id})

    async def get_client(self, client_id: str) -> ClientResult:
        self.ensure_capability(ProviderCapability.GET_CLIENT)
        record = self._clients.get(client_id)
        if record is None:
            raise ClientNotFoundError(details={"client_id": client_id})
        return ClientResult(client_id=client_id, provider=PROVIDER_NAME, raw=dict(record))

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
