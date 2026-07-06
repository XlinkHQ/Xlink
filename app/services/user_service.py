from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update

from app.core.cache import CacheProtocol
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
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


logger = get_logger("xlink.services.user")


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

    async def notify_data_reset(self, user_id: uuid.UUID) -> None:
        user = await self._repo.get(user_id)
        if user is not None:
            await self._notify(events.USER_DATA_RESET, user)

    async def _enforce_owner_quota(
        self, owner_id: uuid.UUID, new_limit_bytes: int | None, *, old_limit_bytes: int | None = None
    ) -> None:
        owner = await self._repo.session.scalar(
            select(User).where(User.id == owner_id).with_for_update()
        )
        if owner is None:
            return
        if owner.admin_user_limit is not None and owner.admin_user_limit > 0 and old_limit_bytes is None:
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

    async def admin_usage(self, admin_id: uuid.UUID) -> dict:
        owner = await self.get(admin_id)
        users_count = await self._repo.session.scalar(
            select(func.count()).select_from(User).where(
                User.owner_id == admin_id, User.removed.is_(False)
            )
        )
        allocated = await self._repo.session.scalar(
            select(func.coalesce(func.sum(User.data_limit_bytes), 0)).where(
                User.owner_id == admin_id,
                User.removed.is_(False),
                User.data_limit_bytes.is_not(None),
            )
        )
        consumed = await self._repo.session.scalar(
            select(func.coalesce(func.sum(User.users_data_usage), 0)).where(
                User.owner_id == admin_id, User.removed.is_(False)
            )
        )
        return {
            "users_count": int(users_count or 0),
            "users_limit": owner.admin_user_limit,
            "traffic_allocated_bytes": int(allocated or 0),
            "traffic_used_bytes": int(consumed or 0),
            "traffic_budget_bytes": owner.admin_traffic_limit_bytes,
        }

    async def create(self, data: UserCreate, *, owner_id: uuid.UUID | None = None) -> User:
        if owner_id is not None:
            await self._enforce_owner_quota(owner_id, data.data_limit_bytes or None)
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

        user.is_sudo = bool(data.is_sudo)
        if data.is_active is not None:
            user.is_active = data.is_active
        if data.all_groups_access is not None:
            user.all_groups_access = data.all_groups_access
        if data.modify_users_access is not None:
            user.modify_users_access = data.modify_users_access
        if data.subscription_url_prefix is not None:
            user.subscription_url_prefix = data.subscription_url_prefix
        if data.admin_user_limit is not None:
            user.admin_user_limit = data.admin_user_limit
        if data.admin_traffic_limit_bytes is not None:
            user.admin_traffic_limit_bytes = data.admin_traffic_limit_bytes
        await self._repo.add(user)
        return user

    async def update_admin(self, user_id: uuid.UUID, data: AdminUpdate) -> User:
        user = await self.get(user_id)
        if user.role is not UserRole.ADMIN:
            raise ValidationError("Not an admin.", code="not_an_admin")
        cascade_active: bool | None = None
        if data.email is not None:
            user.email = data.email.lower() or None
        if data.is_active is not None and data.is_active != user.is_active:
            user.is_active = data.is_active
            cascade_active = data.is_active
        if data.is_sudo is not None:
            user.is_sudo = data.is_sudo
        if data.all_groups_access is not None:
            user.all_groups_access = data.all_groups_access
        if data.modify_users_access is not None:
            user.modify_users_access = data.modify_users_access
        if data.subscription_url_prefix is not None:
            user.subscription_url_prefix = data.subscription_url_prefix or None
        if data.admin_user_limit is not None:
            user.admin_user_limit = data.admin_user_limit or None
        if data.admin_traffic_limit_bytes is not None:
            user.admin_traffic_limit_bytes = data.admin_traffic_limit_bytes or None
        if data.password:
            result = await self.update_password_hash(user, await hash_password_async(data.password))
        else:
            await self._repo.add(user)
            await self._invalidate(user_id)
            result = user
        # Suspending/restoring an admin cascades to all users they own so their
        # configs stop/resume syncing to nodes.
        if cascade_active is not None:
            await self.set_owned_users_active(user_id, active=cascade_active)
        return result

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
        self,
        user_id: uuid.UUID,
        user_agent: str,
        client_ip: str,
        device_limit: int | None,
        *,
        hwid: str = "",
    ) -> bool:
        import hashlib

        from sqlalchemy import func, select

        from app.domain.user_device import UserDevice

        # Prefer a real per-hardware id (X-HWID, sent by clients like Happ/v2rayN):
        # it survives IP changes and is one device = one slot. Fall back to the
        # coarse UA+IP fingerprint only when the client sends no HWID.
        hwid = (hwid or "").strip()
        fingerprint = hwid if hwid else f"{(user_agent or '').strip().lower()}|{client_ip}"
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
            # Lock the user row so concurrent registrations of distinct devices
            # serialize on the count check and cannot together exceed the limit.
            await session.execute(
                select(User.id).where(User.id == user_id).with_for_update()
            )
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

        try:
            async with session.begin_nested():
                session.add(
                    UserDevice(
                        user_id=user_id,
                        device_hash=device_hash,
                        user_agent=(user_agent or "")[:512],
                    )
                )
                await session.flush()
        except IntegrityError:
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
        serviceability_changed = False
        if data.full_name is not None:
            user.full_name = data.full_name
        if data.data_limit_bytes is not None:
            new_limit = data.data_limit_bytes or None
            old_limit = user.data_limit_bytes
            if (
                user.owner_id is not None
                and (new_limit or 0) > (old_limit or 0)
            ):
                await self._enforce_owner_quota(
                    user.owner_id, new_limit, old_limit_bytes=old_limit
                )
            user.data_limit_bytes = new_limit
            serviceability_changed = True
        if data.expire_at is not None:
            user.expire_at = data.expire_at
            serviceability_changed = True
        if data.data_reset_strategy is not None:
            user.data_reset_strategy = data.data_reset_strategy
        if data.on_hold_duration_seconds is not None:
            user.on_hold_duration_seconds = data.on_hold_duration_seconds
        if data.activation_deadline is not None:
            user.activation_deadline = data.activation_deadline

        if data.expire_strategy is not None or data.on_hold is not None:
            strategy, on_hold = _resolve_expiry(data.expire_strategy, data.on_hold, user.expire_at)
            # on_hold_duration is optional (see UserCreate._validate_on_hold); an
            # on-hold user just can't also carry a fixed expire_at.
            if on_hold and user.expire_at is not None:
                raise ValidationError(
                    "An on-hold user cannot also have a fixed expiry.",
                    code="on_hold_conflict",
                )
            user.expire_strategy = strategy
            user.on_hold = on_hold
        if data.device_limit is not None:
            user.device_limit = data.device_limit
        pinned_changed = False
        if data.pinned_node_ids is not None:
            new_pins = [str(n) for n in data.pinned_node_ids]
            pinned_changed = new_pins != (user.pinned_node_ids or [])
            user.pinned_node_ids = new_pins
        await self._repo.add(user)
        if serviceability_changed:
            await self._repo.session.refresh(user, ["users_data_usage"])
            await self._reactivate_recovered(user)
        await self._invalidate(user_id)
        if pinned_changed or serviceability_changed:
            await self._invalidate_user_feed(user_id)
        await self._notify(events.USER_UPDATED, user)
        return user

    async def _invalidate_user_feed(self, user_id: uuid.UUID) -> None:
        # Key layout is subscription:{subject_id}:{scope}:{version}:{format}
        # (subject id FIRST) — the old subscription:*:user:{id} pattern never
        # matched, so quota/expiry edits served stale cached feeds.
        pattern = f"subscription:{user_id}:*"
        try:
            keys = [key async for key in self._cache.client.scan_iter(match=pattern)]
            if keys:
                await self._cache.client.delete(*keys)
        except Exception as exc:
            logger.warning("user_feed_cache_invalidation_failed", error=str(exc))

    async def get(self, user_id: uuid.UUID) -> User:
        user = await self._repo.get(user_id)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")
        return user

    async def assert_can_manage_many(
        self, admin: User, user_ids: list[uuid.UUID], *, skip_missing: bool = False
    ) -> None:
        if not user_ids:
            return
        rows = await self._repo.session.execute(
            select(User).where(User.id.in_(user_ids))
        )
        found = {u.id: u for u in rows.scalars().all()}
        for uid in user_ids:
            target = found.get(uid)
            if target is None:
                # For batch READ endpoints, a user deleted between the list
                # render and this fetch shouldn't 404 the whole page — just skip.
                if skip_missing:
                    continue
                raise NotFoundError("User not found.", code="user_not_found")
            self.assert_can_manage(admin, target)

    async def scoped_group_ids(self, admin_id: uuid.UUID) -> set[uuid.UUID]:
        from app.domain.user import admin_groups

        rows = await self._repo.session.execute(
            select(admin_groups.c.group_id).where(admin_groups.c.admin_id == admin_id)
        )
        return {gid for (gid,) in rows.all()}

    async def scoped_profile_ids(self, admin_id: uuid.UUID) -> set[uuid.UUID]:
        # Profiles a scoped admin may use = the union of profile_ids across the
        # groups granted to them. Used to stop a reseller from pinning a user
        # onto an arbitrary profile/node outside their scope.
        from app.domain.group import Group

        group_ids = await self.scoped_group_ids(admin_id)
        if not group_ids:
            return set()
        rows = await self._repo.session.execute(
            select(Group.profile_ids).where(Group.id.in_(group_ids))
        )
        out: set[uuid.UUID] = set()
        for (pids,) in rows.all():
            for pid in pids or []:
                try:
                    out.add(uuid.UUID(str(pid)))
                except (ValueError, TypeError):
                    continue
        return out

    async def get_by_identifier(self, identifier: str) -> User | None:
        return await self._repo.get_by_identifier(identifier)

    async def update_password_hash(
        self, user: User, hashed_password: str, *, invalidate_tokens: bool = True
    ) -> User:
        user.hashed_password = hashed_password

        if invalidate_tokens:
            user.password_changed_at = datetime.now(UTC)
        await self._repo.add(user)
        if invalidate_tokens:
            # Revoke refresh tokens too: bumping password_changed_at only rejects
            # already-issued access tokens, but a leaked refresh token would keep
            # minting fresh access tokens (each with a current iat) and bypass it.
            from app.core.config import get_settings
            from app.repositories.refresh_token import RefreshTokenRepository
            from app.services.token_service import TokenService

            tokens = TokenService(RefreshTokenRepository(self._repo.session), get_settings())
            await tokens.revoke_all(user.id)
        await self._invalidate(user.id)
        return user

    async def mark_sessions_revoked(self, user_id: uuid.UUID) -> None:
        user = await self.get(user_id)
        user.sessions_revoked_at = datetime.now(UTC)
        await self._repo.add(user)
        await self._invalidate(user_id)

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
        search: str | None = None,
        sort: str | None = None,
    ) -> tuple[Sequence[User], int]:
        return await self._repo.list_paginated(
            offset=params.offset,
            limit=params.limit,
            role=role,
            is_active=is_active,
            include_removed=include_removed,
            owner_id=owner_id,
            search=search,
            sort=sort,
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

    async def iter_all(
        self,
        *,
        role: UserRole | None = None,
        owner_id: uuid.UUID | None = None,
        batch_size: int = 500,
    ):
        offset = 0
        while True:
            rows, total = await self._repo.list_paginated(
                offset=offset,
                limit=batch_size,
                role=role,
                is_active=None,
                include_removed=False,
                owner_id=owner_id,
            )
            for row in rows:
                yield row
            offset += len(rows)
            if not rows or offset >= total:
                break

    async def list_users_keyset(
        self,
        params: CursorParams,
        *,
        role: UserRole | None = None,
        is_active: bool | None = None,
        include_removed: bool = False,
        owner_id: uuid.UUID | None = None,
        search: str | None = None,
        sort: str | None = None,
    ) -> tuple[list[User], str | None]:
        from app.core.pagination import decode_sort_cursor, encode_sort_cursor
        from app.repositories.user import UserRepository

        sort = sort if sort in UserRepository._KEYSET else "newest"
        _, _, attr = UserRepository._KEYSET[sort]

        cursor = None
        if params.cursor is not None:
            try:
                csort, cval, cid = decode_sort_cursor(params.cursor)
                # A cursor minted for a different sort is invalid — restart.
                if csort == sort:
                    # datetime columns were serialized as ISO strings; coerce back
                    # so the keyset comparison uses a real datetime, not a string.
                    if attr in ("created_at", "expire_at") and isinstance(cval, str):
                        from datetime import UTC, datetime

                        cval = datetime.fromisoformat(cval)
                        if cval.tzinfo is None:
                            cval = cval.replace(tzinfo=UTC)
                    cursor = (cval, cid)
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
                search=search,
                sort=sort,
            )
        )

        next_cursor = None
        if len(rows) > params.limit:
            rows = rows[: params.limit]
            last = rows[-1]
            next_cursor = encode_sort_cursor(sort, getattr(last, attr), last.id)
        return rows, next_cursor

    async def bulk_action(
        self,
        action: str,
        user_ids: Sequence[uuid.UUID],
        *,
        admin: User,
        data_limit_bytes: int | None = None,
        expire_at: "datetime | None" = None,
        extend_days: int | None = None,
        data_reset_strategy: str | None = None,
    ) -> dict[str, int]:
        from datetime import UTC, datetime, timedelta

        from app.domain.user import DataResetStrategy

        # Validate value-carrying params once up front so a bad request fails the
        # whole call instead of silently counting every user as "failed".
        strategy_value: DataResetStrategy | None = None
        if action == "set_reset_strategy":
            try:
                strategy_value = DataResetStrategy(data_reset_strategy or "no_reset")
            except ValueError as exc:
                raise ValidationError("Invalid reset strategy.", code="invalid_reset_strategy") from exc
        if action == "extend_expiry" and not extend_days:
            raise ValidationError("extend_days is required.", code="extend_days_required")
        limit_value = data_limit_bytes or None

        ok = 0
        failed = 0
        for uid in user_ids:
            try:
                # Savepoint per user: a failing row rolls back only itself and
                # doesn't poison the outer transaction for the remaining users.
                async with self._repo.session.begin_nested():
                    target = await self.get(uid)
                    self.assert_can_manage(admin, target)
                    if action == "enable":
                        await self.enable(uid)
                    elif action == "disable":
                        await self.disable(uid)
                    elif action == "delete":
                        await self.delete(uid)
                    elif action == "reset_usage":
                        await self._reset_user_usage(uid)
                    elif action == "set_data_limit":
                        if (
                            limit_value is not None
                            and target.owner_id is not None
                            and limit_value > (target.data_limit_bytes or 0)
                        ):
                            await self._enforce_owner_quota(
                                target.owner_id, limit_value, old_limit_bytes=target.data_limit_bytes
                            )
                        target.data_limit_bytes = limit_value
                    elif action == "set_expiry":
                        target.expire_at = expire_at
                    elif action == "extend_expiry":
                        base = target.expire_at or datetime.now(UTC)
                        target.expire_at = base + timedelta(days=extend_days or 0)
                    elif action == "set_reset_strategy":
                        target.data_reset_strategy = strategy_value or DataResetStrategy.NO_RESET
                    else:
                        raise ValidationError("Unknown bulk action.", code="unknown_bulk_action")
                if action in ("set_data_limit", "set_expiry", "extend_expiry", "set_reset_strategy"):
                    await self._invalidate(uid)
                # Raising a limit / extending expiry can make a LIMITED/expired
                # user serviceable again — flip them back to ACTIVE, matching the
                # single-edit update_quota path (else bulk-raise leaves them cut).
                if action in ("set_data_limit", "set_expiry", "extend_expiry"):
                    refreshed = await self.get(uid)
                    await self._repo.session.refresh(refreshed, ["users_data_usage"])
                    await self._reactivate_recovered(refreshed)
                ok += 1
            except Exception as exc:
                # Best-effort per user; log so a genuine failure (vs an authz
                # denial) is diagnosable instead of vanishing into the count.
                logger.warning("bulk_action_skip", action=action, user_id=str(uid), error=str(exc))
                failed += 1
        return {"ok": ok, "failed": failed}

    async def _reset_user_usage(self, user_id: uuid.UUID) -> None:
        from app.traffic.service import TrafficService

        await TrafficService(self._repo.session, cache=self._cache).reset_user(user_id)

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

    async def _reactivate_recovered(self, user: User) -> None:
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
        if user.role is UserRole.ADMIN:
            from sqlalchemy import func

            owned = await self._repo.session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.owner_id == user_id, User.removed.is_(False))
            )
            if (owned or 0) > 0:
                raise ValidationError(
                    f"This admin still owns {owned} user(s) — reassign or remove them first.",
                    code="admin_owns_users",
                )
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
