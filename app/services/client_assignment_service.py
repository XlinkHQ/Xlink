from __future__ import annotations

import uuid

from sqlalchemy import select, update

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.pagination import decode_cursor, encode_cursor
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node
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
from app.services._shared import invalidate_subscription_cache, save_or_conflict

if __import__("typing").TYPE_CHECKING:
    from app.subscription.service import SubscriptionService

logger = get_logger("xlink.assignments")

_INACTIVE_STATUSES = {AssignmentStatus.DISABLED, AssignmentStatus.EXPIRED}


class ClientAssignmentService:
    def __init__(
        self,
        repo: ClientAssignmentRepository,
        users: UserRepository,
        profiles: ProfileRepository,
        nodes: NodeRepository,
        providers: ProviderRegistry,
        subscription_service: SubscriptionService | None = None,
    ) -> None:
        self._repo = repo
        self._users = users
        self._profiles = profiles
        self._nodes = nodes
        self._providers = providers
        self._subscription_service = subscription_service

    async def create(self, data: AssignmentCreate) -> ClientAssignment:
        user = await self._validate_user(data.user_id)
        profile = await self._validate_profile(data.profile_id)

        if data.node_id is None:
            data = data.model_copy(update={"node_id": profile.node_id})
        assert data.node_id is not None

        node = await self._validate_node(data.node_id)

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

        if not await self._reserve_node_slot(data.node_id):
            raise ConflictError(
                "Node has reached its maximum user capacity.",
                code="node_capacity_reached",
                details={"node_id": str(node.id)},
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
            group_id=data.group_id,
        )

        attributes = {
            **profile.settings,
            "profile_slug": profile.slug,
            "protocol": profile.protocol,
        }
        if data.provider_kind == ProviderKind.WIREGUARD:
            attributes["address"] = await self._allocate_wireguard_address(
                data.node_id, profile.settings.get("address")
            )
        spec = ClientSpec(
            client_id=str(assignment.id),
            email=user.email or user.username,
            inbound_tag=profile.slug,
            attributes=attributes,
        )
        try:
            result = await self._provision(provider, spec)
        except Exception:
            await self._release_node_slot(data.node_id)
            raise
        assignment.provider_client_id = result.client_id
        assignment.credentials = dict(result.raw) if isinstance(result.raw, dict) else {}

        try:
            await self._repo.add_pending(assignment)
        except Exception:
            await self._deprovision(provider, result.client_id)
            await self._release_node_slot(data.node_id)
            raise

        await self._repo.session.flush()
        await self._repo.session.refresh(assignment)
        await self._invalidate_subscription_cache(node.id)
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
            old_status = assignment.status
            new_status = data.status
            assignment.status = new_status
            if old_status != new_status:
                if old_status is AssignmentStatus.ACTIVE and new_status in _INACTIVE_STATUSES:
                    await self._adjust_node_users_by_id(assignment.node_id, -1)
                elif old_status in _INACTIVE_STATUSES and new_status is AssignmentStatus.ACTIVE:
                    await self._adjust_node_users_by_id(assignment.node_id, 1)
        if data.expires_at is not None:
            assignment.expires_at = data.expires_at
        if data.traffic_limit_bytes is not None:
            assignment.traffic_limit_bytes = data.traffic_limit_bytes
        result = await self._flush(assignment)
        await self._invalidate_subscription_cache(assignment.node_id)
        return result

    async def disable(self, assignment_id: uuid.UUID) -> ClientAssignment:
        assignment = await self.get(assignment_id)
        was_active = assignment.status is AssignmentStatus.ACTIVE
        assignment.status = AssignmentStatus.DISABLED
        if was_active:
            await self._adjust_node_users_by_id(assignment.node_id, -1)
        result = await self._flush(assignment)
        await self._invalidate_subscription_cache(assignment.node_id)
        return result

    async def delete(self, assignment_id: uuid.UUID) -> None:
        assignment = await self.get(assignment_id)
        was_active = assignment.status is AssignmentStatus.ACTIVE
        provider = self._get_provider(assignment.provider_kind)
        if assignment.provider_client_id is not None:
            await self._deprovision(provider, assignment.provider_client_id)
        if was_active:
            await self._adjust_node_users_by_id(assignment.node_id, -1)
        await self._repo.remove(assignment)
        await self._invalidate_subscription_cache(assignment.node_id)

    async def sync_group(
        self, group_id: uuid.UUID, target_profile_ids: list[uuid.UUID]
    ) -> dict[str, int]:
        target = set(target_profile_ids)
        existing = await self._repo.list_by_group(group_id)
        # Batch-load all target profiles once instead of per-user-per-id (N+1).
        profiles_by_id: dict[uuid.UUID, object] = {}
        if target:
            from sqlalchemy import select as _select

            from app.domain.profile import Profile as _Profile

            rows = (
                await self._repo.session.execute(
                    _select(_Profile).where(_Profile.id.in_(target))
                )
            ).scalars().all()
            profiles_by_id = {p.id: p for p in rows}
        by_user: dict[uuid.UUID, dict[uuid.UUID, ClientAssignment]] = {}
        for a in existing:
            by_user.setdefault(a.user_id, {})[a.profile_id] = a

        added = 0
        removed = 0
        for user_id, owned in by_user.items():
            for profile_id, assignment in list(owned.items()):
                if profile_id not in target:
                    await self.delete(assignment.id)
                    removed += 1
            for profile_id in target - set(owned.keys()):
                profile = profiles_by_id.get(profile_id)
                if profile is None:
                    continue
                try:
                    await self.create(
                        AssignmentCreate(
                            user_id=user_id,
                            profile_id=profile_id,
                            node_id=profile.node_id,
                            provider_kind=profile.provider_kind,
                            group_id=group_id,
                        )
                    )
                    added += 1
                except (ConflictError, ValidationError, ProviderError) as exc:
                    logger.warning("group_sync_skip", user_id=str(user_id), error=str(exc))
        return {"added": added, "removed": removed}

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
        if not profile.is_active:
            raise ValidationError(
                "Profile is not active.",
                code="profile_inactive",
                details={"profile_id": str(profile_id)},
            )
        return profile

    async def _validate_node(self, node_id: uuid.UUID) -> Node:
        from app.domain.node import NodeStatus

        node = await self._nodes.get(node_id)
        if node is None:
            raise ValidationError(
                "Referenced node does not exist.",
                code="invalid_node",
                details={"node_id": str(node_id)},
            )
        if node.status != NodeStatus.ACTIVE:
            raise ValidationError(
                "Node is not active.",
                code="node_not_active",
                details={"node_id": str(node_id), "status": node.status.value},
            )
        return node

    def _adjust_node_users(self, node: Node, delta: int) -> None:
        node.current_users = max(0, node.current_users + delta)

    async def _adjust_node_users_by_id(self, node_id: uuid.UUID, delta: int) -> None:
        node = await self._nodes.get(node_id)
        if node is not None:
            self._adjust_node_users(node, delta)
            await self._repo.session.flush()

    async def _allocate_wireguard_address(
        self, node_id: uuid.UUID, server_address: object
    ) -> str:
        prefix = "10.8.0"
        if isinstance(server_address, str) and "." in server_address:
            head = server_address.split("/")[0].strip().rsplit(".", 1)[0]
            if head:
                prefix = head
        rows = await self._repo.session.execute(
            select(ClientAssignment.credentials).where(
                ClientAssignment.node_id == node_id,
                ClientAssignment.provider_kind == ProviderKind.WIREGUARD,
            )
        )
        used = {1}
        for (creds,) in rows.all():
            addr = (creds or {}).get("address") if isinstance(creds, dict) else None
            if isinstance(addr, str) and "." in addr:
                tail = addr.split("/")[0].strip().rsplit(".", 1)[-1]
                if tail.isdigit():
                    used.add(int(tail))
        octet = 2
        while octet in used and octet < 255:
            octet += 1
        return f"{prefix}.{octet}/32"

    async def _reserve_node_slot(self, node_id: uuid.UUID) -> bool:
        result = await self._repo.session.execute(
            update(Node)
            .where(Node.id == node_id, Node.current_users < Node.max_users)
            .values(current_users=Node.current_users + 1)
            .execution_options(synchronize_session=False)
        )
        await self._repo.session.flush()
        return (result.rowcount or 0) > 0

    async def _release_node_slot(self, node_id: uuid.UUID) -> None:
        await self._repo.session.execute(
            update(Node)
            .where(Node.id == node_id, Node.current_users > 0)
            .values(current_users=Node.current_users - 1)
            .execution_options(synchronize_session=False)
        )
        await self._repo.session.flush()

    async def _invalidate_subscription_cache(self, node_id: uuid.UUID | None = None) -> None:
        await invalidate_subscription_cache(self._subscription_service, node_id)

    async def _flush(self, assignment: ClientAssignment) -> ClientAssignment:
        return await save_or_conflict(self._repo.save, assignment, "Assignment")
