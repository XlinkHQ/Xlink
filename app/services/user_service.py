from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from app.core.cache import CacheProtocol
from app.core.exceptions import NotFoundError, ValidationError
from app.core.pagination import decode_cursor, encode_cursor
from app.core.security import hash_password_async
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.user import User, UserExpireStrategy, UserRole
from app.repositories.user import UserRepository
from app.schemas.pagination import CursorParams, PaginationParams
from app.schemas.user import AdminUpdate, UserCreate, UserUpdate
from app.webhooks import events
from app.webhooks.dispatcher import WebhookDispatcher

if TYPE_CHECKING:
    from app.subscription.service import SubscriptionService

_USER_CACHE_PREFIX = "user:id:"


def _resolve_expiry(
    strategy: UserExpireStrategy | None, on_hold: bool | None, expire_at
) -> tuple[UserExpireStrategy, bool]:
    if strategy is not None:
        return strategy, strategy is UserExpireStrategy.START_ON_FIRST_USE

    if on_hold:
        return UserExpireStrategy.START_ON_FIRST_USE, True
    if expire_at is not None:
        return UserExpireStrategy.FIXED_DATE, False
    return UserExpireStrategy.NEVER, False


class UserService:
    def __init__(
        self,
        repo: UserRepository,
        cache: CacheProtocol,
        webhooks: WebhookDispatcher | None = None,
        subscription_service: SubscriptionService | None = None,
    ) -> None:
        self._repo = repo
        self._cache = cache
        self._webhooks = webhooks
        self._subscription_service = subscription_service

    async def _notify_nodes(self, node_ids: Sequence[uuid.UUID]) -> None:
        if self._subscription_service is None or not node_ids:
            return
        await self._subscription_service.invalidate_cache()
        for nid in node_ids:
            await self._subscription_service.notify_node_changed(nid)

    async def _notify_user_nodes(self, user_id: uuid.UUID) -> None:
        if self._subscription_service is None:
            return
        from sqlalchemy import select as _select

        rows = await self._repo.session.execute(
            _select(ClientAssignment.node_id).where(ClientAssignment.user_id == user_id).distinct()
        )
        await self._notify_nodes([nid for (nid,) in rows.all() if nid is not None])

    async def _notify(self, action: str, user: User) -> None:
        if self._webhooks is not None and user.role is UserRole.USER:
            await self._webhooks.dispatch(action, user.username)

    async def notify_data_reset(self, user_id: uuid.UUID) -> None:
        user = await self._repo.get(user_id)
        if user is not None:
            await self._notify(events.USER_DATA_RESET, user)

    async def create(self, data: UserCreate, *, owner_id: uuid.UUID | None = None) -> User:
        user = await self._create(data, role=UserRole.USER, owner_id=owner_id)
        await self._notify(events.USER_CREATED, user)
        return user

    @staticmethod
    def assert_can_manage(admin: User, user: User) -> None:
        from app.core.authz import Permission, authorize

        authorize(admin, Permission.MANAGE_USER, target=user)

    async def create_admin(self, data: UserCreate) -> User:
        if not data.password:
            raise ValidationError("Admins require a password.", code="password_required")
        user = await self._create(data, role=UserRole.ADMIN)

        user.is_sudo = True if data.is_sudo is None else data.is_sudo
        if data.is_active is not None:
            user.is_active = data.is_active
        if data.all_groups_access is not None:
            user.all_groups_access = data.all_groups_access
        if data.modify_users_access is not None:
            user.modify_users_access = data.modify_users_access
        if data.subscription_url_prefix is not None:
            user.subscription_url_prefix = data.subscription_url_prefix
        await self._repo.add(user)
        return user

    async def update_admin(self, user_id: uuid.UUID, data: AdminUpdate) -> User:
        user = await self.get(user_id)
        if user.role is not UserRole.ADMIN:
            raise ValidationError("Not an admin.", code="not_an_admin")
        if data.email is not None:
            user.email = data.email.lower() or None
        if data.is_active is not None:
            user.is_active = data.is_active
        if data.is_sudo is not None:
            user.is_sudo = data.is_sudo
        if data.all_groups_access is not None:
            user.all_groups_access = data.all_groups_access
        if data.modify_users_access is not None:
            user.modify_users_access = data.modify_users_access
        if data.subscription_url_prefix is not None:
            user.subscription_url_prefix = data.subscription_url_prefix or None
        if data.password:
            return await self.update_password_hash(user, await hash_password_async(data.password))
        await self._repo.add(user)
        await self._invalidate(user_id)
        return user

    async def _create(
        self, data: UserCreate, *, role: UserRole, owner_id: uuid.UUID | None = None
    ) -> User:
        hashed = await hash_password_async(data.password) if data.password else None
        strategy, on_hold = _resolve_expiry(data.expire_strategy, data.on_hold, data.expire_at)
        user = User(
            email=data.email.lower() if data.email else None,
            username=data.username,
            full_name=data.full_name,
            hashed_password=hashed,
            role=role,
            data_limit_bytes=data.data_limit_bytes,
            expire_at=data.expire_at,
            data_reset_strategy=data.data_reset_strategy,
            on_hold=on_hold,
            on_hold_duration_seconds=data.on_hold_duration_seconds,
            expire_strategy=strategy,
            activation_deadline=data.activation_deadline,
            device_limit=data.device_limit,
            owner_id=owner_id,
        )
        return await self._repo.create_user(user)

    async def set_role(self, user_id: uuid.UUID, role: UserRole) -> User:
        user = await self.get(user_id)
        user.role = role
        await self._repo.add(user)
        await self._invalidate(user_id)
        return user

    async def revoke_subscription(self, user_id: uuid.UUID) -> User:
        user = await self.get(user_id)
        user.sub_revision = (user.sub_revision or 0) + 1
        await self._repo.add(user)
        await self._invalidate(user_id)
        return user

    async def touch_subscription(self, user_id: uuid.UUID, user_agent: str) -> None:
        await self._repo.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                sub_updated_at=datetime.now(UTC),
                sub_last_user_agent=(user_agent or "")[:512] or None,
            )
        )

    async def register_device(
        self, user_id: uuid.UUID, user_agent: str, client_ip: str, device_limit: int | None
    ) -> bool:
        import hashlib

        from sqlalchemy import func, select

        from app.domain.user_device import UserDevice

        fingerprint = f"{(user_agent or '').strip().lower()}|{client_ip}"
        device_hash = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:64]
        session = self._repo.session
        existing = (
            await session.execute(
                select(UserDevice).where(
                    UserDevice.user_id == user_id, UserDevice.device_hash == device_hash
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.last_seen_at = datetime.now(UTC)
            await session.flush()
            return True
        if device_limit is not None and device_limit > 0:
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(UserDevice)
                    .where(UserDevice.user_id == user_id)
                )
            ).scalar_one()
            if count >= device_limit:
                return False
        from sqlalchemy.exc import IntegrityError

        session.add(
            UserDevice(
                user_id=user_id,
                device_hash=device_hash,
                user_agent=(user_agent or "")[:512],
            )
        )
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            return True
        return True

    async def list_devices(self, user_id: uuid.UUID) -> list:
        from sqlalchemy import select

        from app.domain.user_device import UserDevice

        rows = (
            (
                await self._repo.session.execute(
                    select(UserDevice)
                    .where(UserDevice.user_id == user_id)
                    .order_by(UserDevice.last_seen_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def reset_devices(self, user_id: uuid.UUID) -> int:
        from sqlalchemy import delete

        from app.domain.user_device import UserDevice

        result = await self._repo.session.execute(
            delete(UserDevice).where(UserDevice.user_id == user_id)
        )
        return result.rowcount or 0

    async def update_quota(self, user_id: uuid.UUID, data: UserUpdate) -> User:
        user = await self.get(user_id)
        if data.full_name is not None:
            user.full_name = data.full_name
        user.data_limit_bytes = data.data_limit_bytes
        user.expire_at = data.expire_at
        if data.data_reset_strategy is not None:
            user.data_reset_strategy = data.data_reset_strategy
        if data.on_hold_duration_seconds is not None:
            user.on_hold_duration_seconds = data.on_hold_duration_seconds
        if data.activation_deadline is not None:
            user.activation_deadline = data.activation_deadline

        if data.expire_strategy is not None or data.on_hold is not None:
            strategy, on_hold = _resolve_expiry(data.expire_strategy, data.on_hold, data.expire_at)
            user.expire_strategy = strategy
            user.on_hold = on_hold
        user.device_limit = data.device_limit
        pinned_changed = False
        if data.pinned_node_ids is not None:
            new_pins = [str(n) for n in data.pinned_node_ids]
            pinned_changed = new_pins != (user.pinned_node_ids or [])
            user.pinned_node_ids = new_pins
        await self._repo.add(user)
        await self._invalidate(user_id)
        if pinned_changed:
            await self._invalidate_user_feed(user_id)
        await self._notify(events.USER_UPDATED, user)
        return user

    async def _invalidate_user_feed(self, user_id: uuid.UUID) -> None:
        pattern = f"subscription:*:user:{user_id}"
        try:
            keys = [key async for key in self._cache.client.scan_iter(match=pattern)]
            if keys:
                await self._cache.client.delete(*keys)
        except Exception:
            pass

    async def get(self, user_id: uuid.UUID) -> User:
        user = await self._repo.get(user_id)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")
        return user

    async def get_by_identifier(self, identifier: str) -> User | None:
        return await self._repo.get_by_identifier(identifier)

    async def update_password_hash(
        self, user: User, hashed_password: str, *, invalidate_tokens: bool = True
    ) -> User:
        user.hashed_password = hashed_password

        if invalidate_tokens:
            user.password_changed_at = datetime.now(UTC)
        await self._repo.add(user)
        await self._invalidate(user.id)
        return user

    async def update_totp_secret(self, user_id: uuid.UUID, secret: str) -> User:
        user = await self.get(user_id)
        user.totp_secret = secret
        user.totp_enabled = False
        await self._repo.add(user)
        await self._invalidate(user_id)
        return user

    async def enable_totp(self, user_id: uuid.UUID) -> User:
        user = await self.get(user_id)
        user.totp_enabled = True
        await self._repo.add(user)
        await self._invalidate(user_id)
        return user

    async def disable_totp(self, user_id: uuid.UUID) -> User:
        user = await self.get(user_id)
        user.totp_secret = None
        user.totp_enabled = False
        await self._repo.add(user)
        await self._invalidate(user_id)
        return user

    async def update_profile(self, user_id: uuid.UUID, data: UserUpdate) -> User:
        user = await self.get(user_id)
        if data.full_name is not None:
            user.full_name = data.full_name
        await self._repo.add(user)
        await self._invalidate(user_id)
        return user

    async def list_users(
        self,
        params: PaginationParams,
        *,
        role: UserRole | None = None,
        is_active: bool | None = None,
        include_removed: bool = False,
        owner_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[User], int]:
        return await self._repo.list_paginated(
            offset=params.offset,
            limit=params.limit,
            role=role,
            is_active=is_active,
            include_removed=include_removed,
            owner_id=owner_id,
        )

    async def list_all(
        self,
        *,
        role: UserRole | None = None,
        owner_id: uuid.UUID | None = None,
    ) -> list[User]:
        collected: list[User] = []
        offset = 0
        while True:
            rows, total = await self._repo.list_paginated(
                offset=offset,
                limit=500,
                role=role,
                is_active=None,
                include_removed=False,
                owner_id=owner_id,
            )
            collected.extend(rows)
            offset += len(rows)
            if not rows or offset >= total:
                break
        return collected

    async def list_users_keyset(
        self,
        params: CursorParams,
        *,
        role: UserRole | None = None,
        is_active: bool | None = None,
        include_removed: bool = False,
        owner_id: uuid.UUID | None = None,
    ) -> tuple[list[User], str | None]:
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
                role=role,
                is_active=is_active,
                include_removed=include_removed,
                owner_id=owner_id,
            )
        )

        next_cursor = None
        if len(rows) > params.limit:
            rows = rows[: params.limit]
            last = rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)
        return rows, next_cursor

    async def disable(self, user_id: uuid.UUID) -> User:
        user = await self.get(user_id)
        node_ids = await self._active_node_ids(user_id)
        user.is_active = False
        await self._repo.add(user)

        stmt = (
            update(ClientAssignment)
            .where(
                ClientAssignment.user_id == user_id,
                ClientAssignment.status == AssignmentStatus.ACTIVE,
            )
            .values(status=AssignmentStatus.DISABLED)
        )
        await self._repo.session.execute(stmt)
        await self._resync_node_counts(node_ids)
        await self._notify_user_nodes(user_id)
        await self._invalidate(user_id)
        await self._notify(events.USER_DISABLED, user)
        return user

    async def enable(self, user_id: uuid.UUID) -> User:
        user = await self.get(user_id)
        node_rows = await self._repo.session.execute(
            select(ClientAssignment.node_id)
            .where(
                ClientAssignment.user_id == user_id,
                ClientAssignment.status == AssignmentStatus.DISABLED,
            )
            .distinct()
        )
        node_ids = [nid for (nid,) in node_rows.all() if nid is not None]
        user.is_active = True
        await self._repo.add(user)

        stmt = (
            update(ClientAssignment)
            .where(
                ClientAssignment.user_id == user_id,
                ClientAssignment.status == AssignmentStatus.DISABLED,
            )
            .values(status=AssignmentStatus.ACTIVE)
        )
        await self._repo.session.execute(stmt)
        await self._resync_node_counts(node_ids)
        await self._notify_user_nodes(user_id)
        await self._invalidate(user_id)
        await self._notify(events.USER_ENABLED, user)
        return user

    async def set_owned_users_active(self, admin_id: uuid.UUID, *, active: bool) -> int:
        admin = await self.get(admin_id)
        if admin.role is not UserRole.ADMIN:
            raise ValidationError("Not an admin.", code="not_an_admin")
        ids = (
            (
                await self._repo.session.execute(
                    select(User.id).where(
                        User.owner_id == admin_id,
                        User.role == UserRole.USER,
                        User.removed.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not ids:
            return 0
        await self._repo.session.execute(
            update(User).where(User.id.in_(ids)).values(is_active=active)
        )
        await self._repo.session.execute(
            update(ClientAssignment)
            .where(
                ClientAssignment.user_id.in_(ids),
                ClientAssignment.status
                == (AssignmentStatus.DISABLED if active else AssignmentStatus.ACTIVE),
            )
            .values(status=AssignmentStatus.ACTIVE if active else AssignmentStatus.DISABLED)
        )
        node_rows = await self._repo.session.execute(
            select(ClientAssignment.node_id).where(ClientAssignment.user_id.in_(ids)).distinct()
        )
        affected_node_ids = [nid for (nid,) in node_rows.all() if nid is not None]
        await self._resync_node_counts(affected_node_ids)
        await self._notify_nodes(affected_node_ids)
        for uid in ids:
            await self._invalidate(uid)
        return len(ids)

    async def delete(self, user_id: uuid.UUID) -> None:
        user = await self.get(user_id)
        node_ids = await self._active_node_ids(user_id)
        user.removed = True
        user.is_active = False
        await self._repo.add(user)
        stmt = (
            update(ClientAssignment)
            .where(
                ClientAssignment.user_id == user_id,
                ClientAssignment.status == AssignmentStatus.ACTIVE,
            )
            .values(status=AssignmentStatus.DISABLED)
        )
        await self._repo.session.execute(stmt)
        await self._resync_node_counts(node_ids)
        await self._notify_nodes(node_ids)
        await self._invalidate(user_id)
        await self._notify(events.USER_DELETED, user)

    async def restore(self, user_id: uuid.UUID) -> User:
        user = await self.get(user_id)
        user.removed = False
        await self._repo.add(user)
        await self._invalidate(user_id)
        return user

    async def purge(self, user_id: uuid.UUID) -> None:
        user = await self.get(user_id)
        node_ids = await self._active_node_ids(user_id)
        await self._repo.session.delete(user)
        await self._repo.session.flush()
        await self._resync_node_counts(node_ids)
        await self._notify_nodes(node_ids)
        await self._invalidate(user_id)
        await self._notify(events.USER_DELETED, user)

    async def _active_node_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        rows = await self._repo.session.execute(
            select(ClientAssignment.node_id)
            .where(
                ClientAssignment.user_id == user_id,
                ClientAssignment.status == AssignmentStatus.ACTIVE,
            )
            .distinct()
        )
        return [nid for (nid,) in rows.all()]

    async def _resync_node_counts(self, node_ids: Sequence[uuid.UUID]) -> None:
        if not node_ids:
            return
        from sqlalchemy import func

        from app.domain.node import Node

        active_count = (
            select(func.count())
            .select_from(ClientAssignment)
            .where(
                ClientAssignment.node_id == Node.id,
                ClientAssignment.status == AssignmentStatus.ACTIVE,
            )
            .scalar_subquery()
        )
        await self._repo.session.execute(
            update(Node)
            .where(Node.id.in_(list(node_ids)))
            .values(current_users=active_count)
            .execution_options(synchronize_session=False)
        )
        await self._repo.session.flush()

    async def _invalidate(self, user_id: uuid.UUID) -> None:
        await self._cache.delete(f"{_USER_CACHE_PREFIX}{user_id}")
