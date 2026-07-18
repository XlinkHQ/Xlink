from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update

from app.core.cache import CacheProtocol
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.user import User, UserExpireStrategy, UserRole
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate
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


logger = get_logger("xlink.services.user")


class UserServiceBase:
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

    @staticmethod
    def assert_can_manage(admin: User, user: User) -> None:
        from app.core.authz import Permission, authorize

        authorize(admin, Permission.MANAGE_USER, target=user)

    async def get(self, user_id: uuid.UUID) -> User:
        user = await self._repo.get(user_id)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")
        return user

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
            await self._apply_notification_overrides()
            await self._webhooks.dispatch(action, user.username)

    async def _apply_notification_overrides(self) -> None:
        # The dispatcher is built per-request from env Settings only; load the
        # UI-configured channels (stored in AppSettings) so lifecycle webhooks
        # honor them, matching the background NotificationJob behavior.
        if self._webhooks is None:
            return
        from app.domain.app_settings import AppSettings

        row = await self._repo.session.get(AppSettings, 1)
        if row is None:
            return
        self._webhooks.apply_overrides(
            webhook_address=row.webhook_address,
            discord_webhook_url=row.discord_webhook_url,
            telegram_bot_token=row.telegram_bot_token,
            telegram_chat_ids=row.telegram_chat_ids,
        )

    async def _create(
        self, data: UserCreate, *, role: UserRole, owner_id: uuid.UUID | None = None
    ) -> User:
        from app.core.security import hash_password_async

        hashed = await hash_password_async(data.password) if data.password else None
        strategy, on_hold = _resolve_expiry(data.expire_strategy, data.on_hold, data.expire_at)
        user = User(
            email=data.email.lower() if data.email else None,
            username=data.username,
            full_name=data.full_name,
            hashed_password=hashed,
            role=role,
            data_limit_bytes=data.data_limit_bytes or None,
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

    async def _enforce_owner_quota(
        self,
        owner_id: uuid.UUID,
        new_limit_bytes: int | None,
        *,
        old_limit_bytes: int | None = None,
        is_update: bool = False,
    ) -> None:
        owner = await self._repo.session.scalar(
            select(User).where(User.id == owner_id).with_for_update()
        )
        if owner is None:
            return
        # The user-COUNT cap only applies when adding a user. An update never adds
        # a user, so gate on is_update — NOT on `old_limit_bytes is None`, which is
        # also true when updating an existing *unlimited* user and would wrongly
        # reject that edit once the owner is at their user cap.
        if (
            not is_update
            and owner.admin_user_limit is not None
            and owner.admin_user_limit > 0
        ):
            count = await self._repo.session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.owner_id == owner_id, User.removed.is_(False))
            )
            if (count or 0) >= owner.admin_user_limit:
                raise ValidationError(
                    f"User limit reached ({owner.admin_user_limit}). Contact your administrator.",
                    code="admin_user_limit",
                )
        if owner.admin_traffic_limit_bytes is not None and owner.admin_traffic_limit_bytes > 0:
            used = await self._repo.session.scalar(
                select(func.coalesce(func.sum(User.data_limit_bytes), 0)).where(
                    User.owner_id == owner_id,
                    User.removed.is_(False),
                    User.data_limit_bytes.is_not(None),
                )
            )
            projected = (used or 0) - (old_limit_bytes or 0) + (new_limit_bytes or 0)
            if projected > owner.admin_traffic_limit_bytes:
                raise ValidationError(
                    "Traffic budget exceeded for your account. Contact your administrator.",
                    code="admin_traffic_limit",
                )

    async def _reactivate_recovered(self, user: User) -> None:
        from datetime import UTC, datetime

        if not user.is_active or user.removed:
            return
        now = datetime.now(UTC)
        under_limit = (
            user.data_limit_bytes is None
            or (user.users_data_usage or 0) < user.data_limit_bytes
        )
        not_expired = user.expire_at is None or user.expire_at > now
        recover = []
        if under_limit:
            recover.append(AssignmentStatus.LIMITED)
        if not_expired:
            recover.append(AssignmentStatus.EXPIRED)
        if not recover:
            return
        node_rows = await self._repo.session.execute(
            select(ClientAssignment.node_id)
            .where(
                ClientAssignment.user_id == user.id,
                ClientAssignment.status.in_(recover),
            )
            .distinct()
        )
        node_ids = [nid for (nid,) in node_rows.all() if nid is not None]
        if not node_ids:
            return
        await self._repo.session.execute(
            update(ClientAssignment)
            .where(
                ClientAssignment.user_id == user.id,
                ClientAssignment.status.in_(recover),
            )
            .values(status=AssignmentStatus.ACTIVE)
        )
        await self._resync_node_counts(node_ids)
        await self._notify_user_nodes(user.id)

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

    async def _invalidate_user_feed(self, user_id: uuid.UUID) -> None:
        # O(1) invalidation: bump the user's per-subject cache revision so their
        # cached feed keys (which embed the revision) go stale at once. Replaces the
        # old SCAN+DEL over subscription:{user_id}:* — that recomputed every feed
        # for the user in a burst and scanned the keyspace on a hot mutation path.
        try:
            if self._subscription_service is not None:
                await self._subscription_service.invalidate_subject(user_id)
            else:
                await self._cache.incr(f"subscription:rev:{user_id}")
        except Exception as exc:
            logger.warning("user_feed_cache_invalidation_failed", error=str(exc))
