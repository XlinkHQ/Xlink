from __future__ import annotations

import uuid

from sqlalchemy.orm.exc import StaleDataError

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.pagination import decode_cursor, encode_cursor
from app.domain.profile import Profile
from app.providers.base.exceptions import ProviderNotFoundError
from app.providers.base.models import ProviderKind
from app.providers.base.registry import ProviderRegistry
from app.repositories.node import NodeRepository
from app.repositories.profile import ProfileRepository
from app.schemas.pagination import CursorParams
from app.schemas.profile import ProfileCreate, ProfileUpdate


class ProfileService:
    def __init__(
        self,
        repo: ProfileRepository,
        node_repo: NodeRepository,
        providers: ProviderRegistry,
    ) -> None:
        self._repo = repo
        self._nodes = node_repo
        self._providers = providers

    async def create(self, data: ProfileCreate) -> Profile:
        self._validate_provider_kind(data.provider_kind)
        await self._validate_node(data.node_id)

        profile = Profile(
            name=data.name,
            slug=data.slug,
            provider_kind=data.provider_kind,
            node_id=data.node_id,
            protocol=data.protocol,
            settings=data.settings,
            is_active=True,
        )
        return await self._repo.create_profile(profile)

    async def get(self, profile_id: uuid.UUID) -> Profile:
        profile = await self._repo.get(profile_id)
        if profile is None:
            raise NotFoundError("Profile not found.", code="profile_not_found")
        return profile

    async def update(self, profile_id: uuid.UUID, data: ProfileUpdate) -> Profile:
        profile = await self.get(profile_id)
        if data.expected_version is not None and data.expected_version != profile.version:
            raise ConflictError("Profile was modified concurrently.", code="version_conflict")

        if data.name is not None:
            profile.name = data.name
        if data.protocol is not None:
            profile.protocol = data.protocol
        if data.settings is not None:
            profile.settings = data.settings
        if data.is_active is not None:
            profile.is_active = data.is_active

        return await self._flush(profile)

    async def set_active(self, profile_id: uuid.UUID, is_active: bool) -> Profile:
        profile = await self.get(profile_id)
        profile.is_active = is_active
        return await self._flush(profile)

    async def disable(self, profile_id: uuid.UUID) -> Profile:
        return await self.set_active(profile_id, False)

    async def list_profiles_keyset(
        self,
        params: CursorParams,
        *,
        provider_kind: ProviderKind | None = None,
        node_id: uuid.UUID | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[Profile], str | None]:
        cursor = None
        if params.cursor is not None:
            try:
                cursor = decode_cursor(params.cursor)
            except ValueError as exc:
                raise ValidationError(str(exc), code="invalid_cursor") from exc

        rows = list(
            await self._repo.list_keyset(
                limit=params.limit + 1,
                cursor=cursor,
                provider_kind=provider_kind,
                node_id=node_id,
                is_active=is_active,
            )
        )

        next_cursor = None
        if len(rows) > params.limit:
            rows = rows[: params.limit]
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)
        return rows, next_cursor

    def _validate_provider_kind(self, kind: ProviderKind) -> None:
        try:
            self._providers.get_by_kind(kind)
        except ProviderNotFoundError as exc:
            raise ValidationError(
                f"No provider registered for kind '{kind.value}'.",
                code="invalid_provider",
                details={"provider_kind": kind.value},
            ) from exc

    async def _validate_node(self, node_id: uuid.UUID) -> None:
        node = await self._nodes.get(node_id)
        if node is None:
            raise ValidationError(
                "Referenced node does not exist.",
                code="invalid_node",
                details={"node_id": str(node_id)},
            )

    async def _flush(self, profile: Profile) -> Profile:
        try:
            return await self._repo.save(profile)
        except StaleDataError as exc:
            raise ConflictError(
                "Profile was modified concurrently.", code="version_conflict"
            ) from exc
