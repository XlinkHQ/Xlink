from __future__ import annotations

import uuid

from sqlalchemy.orm.exc import StaleDataError

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.pagination import decode_cursor, encode_cursor
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.user import User
from app.providers.base.exceptions import ProviderError, ProviderNotFoundError
from app.providers.base.models import ClientSpec, ProviderKind
from app.providers.base.provider import Provider
from app.providers.base.registry import ProviderRegistry
from app.repositories.client_assignment import ClientAssignmentRepository
from app.repositories.node import NodeRepository
from app.repositories.profile import ProfileRepository
from app.repositories.user import UserRepository
from app.schemas.client_assignment import AssignmentCreate, AssignmentUpdate
from app.schemas.pagination import CursorParams


class ClientAssignmentService:
    def __init__(
        self,
        repo: ClientAssignmentRepository,
        users: UserRepository,
        profiles: ProfileRepository,
        nodes: NodeRepository,
        providers: ProviderRegistry,
    ) -> None:
        self._repo = repo
        self._users = users
        self._profiles = profiles
        self._nodes = nodes
        self._providers = providers

    async def create(self, data: AssignmentCreate) -> ClientAssignment:
        user = await self._validate_user(data.user_id)
        profile = await self._validate_profile(data.profile_id)
        await self._validate_node(data.node_id)

        if profile.node_id != data.node_id:
            raise ValidationError(
                "Profile does not belong to the given node.", code="profile_node_mismatch"
            )
        if profile.provider_kind != data.provider_kind:
            raise ValidationError(
                "Profile provider kind does not match.", code="profile_provider_mismatch"
            )

        if await self._repo.triplet_exists(data.user_id, data.profile_id, data.node_id):
            raise ConflictError(
                "Assignment already exists for this user, profile and node.",
                code="assignment_exists",
            )

        provider = self._get_provider(data.provider_kind)

        assignment = ClientAssignment(
            id=uuid.uuid4(),
            user_id=data.user_id,
            profile_id=data.profile_id,
            node_id=data.node_id,
            provider_kind=data.provider_kind,
            status=AssignmentStatus.ACTIVE,
            expires_at=data.expires_at,
            traffic_limit_bytes=data.traffic_limit_bytes,
        )

        spec = ClientSpec(
            client_id=str(assignment.id),
            email=user.email,
            inbound_tag=profile.slug,
            attributes={
                **profile.settings,
                "profile_slug": profile.slug,
                "protocol": profile.protocol,
            },
        )
        result = await self._provision(provider, spec)
        assignment.provider_client_id = result.client_id

        try:
            await self._repo.add_pending(assignment)
        except Exception:
            await self._deprovision(provider, result.client_id)
            raise

        await self._repo.session.refresh(assignment)
        return assignment

    async def get(self, assignment_id: uuid.UUID) -> ClientAssignment:
        assignment = await self._repo.get(assignment_id)
        if assignment is None:
            raise NotFoundError("Assignment not found.", code="assignment_not_found")
        return assignment

    async def update(self, assignment_id: uuid.UUID, data: AssignmentUpdate) -> ClientAssignment:
        assignment = await self.get(assignment_id)
        if data.expected_version is not None and data.expected_version != assignment.version:
            raise ConflictError("Assignment was modified concurrently.", code="version_conflict")
        if data.status is not None:
            assignment.status = data.status
        if data.expires_at is not None:
            assignment.expires_at = data.expires_at
        if data.traffic_limit_bytes is not None:
            assignment.traffic_limit_bytes = data.traffic_limit_bytes
        return await self._flush(assignment)

    async def disable(self, assignment_id: uuid.UUID) -> ClientAssignment:
        assignment = await self.get(assignment_id)
        assignment.status = AssignmentStatus.DISABLED
        return await self._flush(assignment)

    async def delete(self, assignment_id: uuid.UUID) -> None:
        assignment = await self.get(assignment_id)
        provider = self._get_provider(assignment.provider_kind)
        if assignment.provider_client_id is not None:
            await self._deprovision(provider, assignment.provider_client_id)
        await self._repo.remove(assignment)

    async def list_keyset(
        self,
        params: CursorParams,
        *,
        user_id: uuid.UUID | None = None,
        profile_id: uuid.UUID | None = None,
        node_id: uuid.UUID | None = None,
        provider_kind: ProviderKind | None = None,
        status: AssignmentStatus | None = None,
    ) -> tuple[list[ClientAssignment], str | None]:
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
                user_id=user_id,
                profile_id=profile_id,
                node_id=node_id,
                provider_kind=provider_kind,
                status=status,
            )
        )
        next_cursor = None
        if len(rows) > params.limit:
            rows = rows[: params.limit]
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)
        return rows, next_cursor

    async def _provision(self, provider: Provider, spec: ClientSpec):
        try:
            return await provider.create_client(spec)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                "Provider failed to create client.", code="provider_create_failed"
            ) from exc

    async def _deprovision(self, provider: Provider, client_id: str) -> None:
        try:
            await provider.delete_client(client_id)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                "Provider failed to delete client.", code="provider_delete_failed"
            ) from exc

    def _get_provider(self, kind: ProviderKind) -> Provider:
        try:
            return self._providers.get_by_kind(kind)
        except ProviderNotFoundError as exc:
            raise ValidationError(
                f"No provider registered for kind '{kind.value}'.",
                code="invalid_provider",
                details={"provider_kind": kind.value},
            ) from exc

    async def _validate_user(self, user_id: uuid.UUID) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise ValidationError(
                "Referenced user does not exist.",
                code="invalid_user",
                details={"user_id": str(user_id)},
            )
        return user

    async def _validate_profile(self, profile_id: uuid.UUID):
        profile = await self._profiles.get(profile_id)
        if profile is None:
            raise ValidationError(
                "Referenced profile does not exist.",
                code="invalid_profile",
                details={"profile_id": str(profile_id)},
            )
        return profile

    async def _validate_node(self, node_id: uuid.UUID) -> None:
        if await self._nodes.get(node_id) is None:
            raise ValidationError(
                "Referenced node does not exist.",
                code="invalid_node",
                details={"node_id": str(node_id)},
            )

    async def _flush(self, assignment: ClientAssignment) -> ClientAssignment:
        try:
            return await self._repo.save(assignment)
        except StaleDataError as exc:
            raise ConflictError(
                "Assignment was modified concurrently.", code="version_conflict"
            ) from exc
