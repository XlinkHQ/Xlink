from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import update

from app.core.exceptions import ValidationError
from app.domain.user import User, UserRole
from app.schemas.pagination import CursorParams, PaginationParams
from app.schemas.user import UserCreate, UserUpdate
from app.services.user_service_base import UserServiceBase, _resolve_expiry
from app.webhooks import events


class UserService(UserServiceBase):
    async def create(self, data: UserCreate, *, owner_id: uuid.UUID | None = None) -> User:
        if owner_id is not None:
            await self._enforce_owner_quota(owner_id, data.data_limit_bytes or None)
        user = await self._create(data, role=UserRole.USER, owner_id=owner_id)
        await self._notify(events.USER_CREATED, user)
        return user

    async def get_by_identifier(self, identifier: str) -> User | None:
        return await self._repo.get_by_identifier(identifier)

    async def notify_data_reset(self, user_id: uuid.UUID) -> None:
        user = await self._repo.get(user_id)
        if user is not None:
            await self._notify(events.USER_DATA_RESET, user)

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

    async def update_quota(self, user_id: uuid.UUID, data: UserUpdate) -> User:
        user = await self.get(user_id)
        serviceability_changed = False
        provided = data.model_fields_set
        if "full_name" in provided:
            user.full_name = data.full_name
        if "data_limit_bytes" in provided:
            new_limit = data.data_limit_bytes or None
            old_limit = user.data_limit_bytes
            if user.owner_id is not None and (new_limit or 0) > (old_limit or 0):
                await self._enforce_owner_quota(
                    user.owner_id, new_limit, old_limit_bytes=old_limit, is_update=True
                )
            user.data_limit_bytes = new_limit
            serviceability_changed = True
        if "expire_at" in provided:
            user.expire_at = data.expire_at
            serviceability_changed = True
        if data.data_reset_strategy is not None:
            user.data_reset_strategy = data.data_reset_strategy
        if "on_hold_duration_seconds" in provided:
            user.on_hold_duration_seconds = data.on_hold_duration_seconds
        if "activation_deadline" in provided:
            user.activation_deadline = data.activation_deadline

        if data.expire_strategy is not None or data.on_hold is not None:
            strategy, on_hold = _resolve_expiry(data.expire_strategy, data.on_hold, user.expire_at)
            if on_hold and user.expire_at is not None:
                raise ValidationError(
                    "An on-hold user cannot also have a fixed expiry.",
                    code="on_hold_conflict",
                )
            user.expire_strategy = strategy
            user.on_hold = on_hold
        if "device_limit" in provided:
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
                if csort == sort:
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

    async def disable(self, user_id: uuid.UUID) -> User:
        from app.domain.client_assignment import AssignmentStatus, ClientAssignment

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
        from sqlalchemy import select

        from app.domain.client_assignment import AssignmentStatus, ClientAssignment

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

    async def delete(self, user_id: uuid.UUID) -> None:
        from app.domain.client_assignment import AssignmentStatus, ClientAssignment

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
            from sqlalchemy import func, select

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
