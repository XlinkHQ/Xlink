from __future__ import annotations

import base64
import secrets
import uuid

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from fastapi import APIRouter, status
from pydantic import BaseModel

from app.core.authz import redact_settings
from app.dependencies.auth import AdminUser, SudoAdminUser
from app.dependencies.pagination import CursorPaginationDep
from app.dependencies.services import ProfileServiceDep
from app.domain.user import User
from app.providers.base.models import ProviderKind
from app.schemas.pagination import CursorPage
from app.schemas.profile import ProfileCreate, ProfileRead, ProfileUpdate

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _read(profile, actor: User) -> ProfileRead:
    # Mask secret settings (reality/wg private keys, passwords) for non-sudo
    # resellers so they can't harvest other tenants' credentials via list/get.
    read = ProfileRead.model_validate(profile)
    read.settings = redact_settings(read.settings, actor)
    return read


def _x25519(urlsafe: bool) -> tuple[str, str]:
    key = X25519PrivateKey.generate()
    priv = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    if urlsafe:
        return (
            base64.urlsafe_b64encode(priv).rstrip(b"=").decode(),
            base64.urlsafe_b64encode(pub).rstrip(b"=").decode(),
        )
    return base64.b64encode(priv).decode(), base64.b64encode(pub).decode()


class KeyGenRequest(BaseModel):
    protocol: str
    security: str = "none"


@router.post("/keys")
async def generate_profile_keys(payload: KeyGenRequest, _admin: AdminUser) -> dict[str, str]:
    if payload.security == "reality":
        priv, pub = _x25519(urlsafe=True)
        return {"privateKey": priv, "publicKey": pub, "shortId": secrets.token_hex(8)}
    if payload.protocol == "wireguard":
        priv, pub = _x25519(urlsafe=False)
        return {
            "privateKey": priv,
            "publicKey": pub,
            "presharedKey": base64.b64encode(secrets.token_bytes(32)).decode(),
            "address": "10.8.0.1/24",
            "allowedIPs": "0.0.0.0/0",
            "dns": "1.1.1.1",
            "mtu": "1420",
        }
    return {}


@router.post("", response_model=ProfileRead, status_code=status.HTTP_201_CREATED)
async def create_profile(
    payload: ProfileCreate,
    _admin: SudoAdminUser,
    profiles: ProfileServiceDep,
) -> ProfileRead:
    profile = await profiles.create(payload)
    return ProfileRead.model_validate(profile)


@router.get("", response_model=CursorPage[ProfileRead])
async def list_profiles(
    _admin: AdminUser,
    pagination: CursorPaginationDep,
    profiles: ProfileServiceDep,
    provider_kind: ProviderKind | None = None,
    node_id: uuid.UUID | None = None,
    is_active: bool | None = None,
) -> CursorPage[ProfileRead]:
    rows, next_cursor = await profiles.list_profiles_keyset(
        pagination,
        provider_kind=provider_kind,
        node_id=node_id,
        is_active=is_active,
    )
    items = [_read(p, _admin) for p in rows]
    return CursorPage(items=items, next_cursor=next_cursor, size=pagination.size)


@router.get("/{profile_id}", response_model=ProfileRead)
async def get_profile(
    profile_id: uuid.UUID,
    _admin: AdminUser,
    profiles: ProfileServiceDep,
) -> ProfileRead:
    profile = await profiles.get(profile_id)
    return _read(profile, _admin)


@router.patch("/{profile_id}", response_model=ProfileRead)
async def update_profile(
    profile_id: uuid.UUID,
    payload: ProfileUpdate,
    _admin: SudoAdminUser,
    profiles: ProfileServiceDep,
) -> ProfileRead:
    profile = await profiles.update(profile_id, payload)
    return ProfileRead.model_validate(profile)


@router.post("/{profile_id}/disable", response_model=ProfileRead)
async def disable_profile(
    profile_id: uuid.UUID,
    _admin: SudoAdminUser,
    profiles: ProfileServiceDep,
) -> ProfileRead:
    profile = await profiles.disable(profile_id)
    return ProfileRead.model_validate(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: uuid.UUID,
    _admin: SudoAdminUser,
    profiles: ProfileServiceDep,
) -> None:
    await profiles.delete(profile_id)
