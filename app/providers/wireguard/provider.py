from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

from app.providers.base.exceptions import ClientNotFoundError
from app.providers.base.models import (
    ClientResult,
    ClientSpec,
    ProviderCapability,
    ProviderKind,
    ProviderMetadata,
)
from app.providers.base.provider import Provider
from app.providers.base.store import JsonClientStore

PROVIDER_NAME = "wireguard"

_CAPABILITIES = frozenset(
    {
        ProviderCapability.CREATE_CLIENT,
        ProviderCapability.UPDATE_CLIENT,
        ProviderCapability.DELETE_CLIENT,
        ProviderCapability.GET_CLIENT,
    }
)

_ECHO_KEYS = ("address", "dns", "allowedIPs")


def _generate_keypair() -> tuple[str, str]:
    private = x25519.X25519PrivateKey.generate()
    private_raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return (
        base64.standard_b64encode(private_raw).decode("ascii"),
        base64.standard_b64encode(public_raw).decode("ascii"),
    )


class WireGuardProvider(Provider):
    def __init__(self, *, data_dir: str | None = None) -> None:
        self._clients = JsonClientStore(PROVIDER_NAME, data_dir=data_dir)

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name=PROVIDER_NAME,
            kind=ProviderKind.WIREGUARD,
            capabilities=_CAPABILITIES,
        )

    async def create_client(self, spec: ClientSpec) -> ClientResult:
        self.ensure_capability(ProviderCapability.CREATE_CLIENT)
        if spec.client_id in self._clients:
            return self._store(spec, existing=self._clients[spec.client_id])
        return self._store(spec)

    async def update_client(self, spec: ClientSpec) -> ClientResult:
        self.ensure_capability(ProviderCapability.UPDATE_CLIENT)
        if spec.client_id not in self._clients:
            return self._store(spec)
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
        if existing is not None:
            private_key = existing["private_key"]
            public_key = existing["public_key"]
        else:
            private_key, public_key = _generate_keypair()

        record: dict[str, str] = {"private_key": private_key, "public_key": public_key}
        for key in _ECHO_KEYS:
            if key in spec.attributes:
                record[key] = str(spec.attributes[key])
            elif existing is not None and key in existing:
                record[key] = existing[key]
        self._clients[spec.client_id] = record
        return ClientResult(client_id=spec.client_id, provider=PROVIDER_NAME, raw=dict(record))
