from __future__ import annotations

import uuid

from sqlalchemy import func, select, update

from app.core.exceptions import ValidationError
from app.core.security import hash_password_async
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.user import User, UserRole
from app.schemas.user import AdminUpdate, UserCreate
from app.services.user_service_base import UserServiceBase


class AdminService(UserServiceBase):
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
        from app.services.user_totp_service import UserTotpService

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
            totp = UserTotpService(
                self._repo, self._cache, self._webhooks, self._subscription_service
            )
            result = await totp.update_password_hash(user, await hash_password_async(data.password))
        else:
            await self._repo.add(user)
            await self._invalidate(user_id)
            result = user
        if cascade_active is not None:
            await self.set_owned_users_active(user_id, active=cascade_active)
        return result

    async def set_role(self, user_id: uuid.UUID, role: UserRole) -> User:
        user = await self.get(user_id)
        user.role = role
        await self._repo.add(user)
        await self._invalidate(user_id)
        return user

    async def assert_can_manage_many(
        self, admin: User, user_ids: list[uuid.UUID], *, skip_missing: bool = False
    ) -> None:
        from app.core.exceptions import NotFoundError

        if not user_ids:
            return
        rows = await self._repo.session.execute(
            select(User).where(User.id.in_(user_ids))
        )
        found = {u.id: u for u in rows.scalars().all()}
        for uid in user_ids:
            target = found.get(uid)
            if target is None:
                if skip_missing:
                    continue
                raise NotFoundError("User not found.", code="user_not_found")
            self.assert_can_manage(admin, target)

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

    async def scoped_group_ids(self, admin_id: uuid.UUID) -> set[uuid.UUID]:
        from app.domain.user import admin_groups

        rows = await self._repo.session.execute(
            select(admin_groups.c.group_id).where(admin_groups.c.admin_id == admin_id)
        )
        return {gid for (gid,) in rows.all()}

    async def scoped_profile_ids(self, admin_id: uuid.UUID) -> set[uuid.UUID]:
        from app.repositories.group import GroupRepository

        group_ids = await self.scoped_group_ids(admin_id)
        if not group_ids:
            return set()
        return await GroupRepository(self._repo.session).profile_ids_for_groups(group_ids)

    async def set_owned_users_active(self, admin_id: uuid.UUID, *, active: bool) -> int:
        admin = await self.get(admin_id)
        if admin.role is not UserRole.ADMIN:
            raise ValidationError("Not an admin.", code="not_an_admin")
        base = [
            User.owner_id == admin_id,
            User.role == UserRole.USER,
            User.removed.is_(False),
        ]
        if active:
            base.append(User.suspended_by_owner.is_(True))
        else:
            base.append(User.is_active.is_(True))
        ids = (
            (await self._repo.session.execute(select(User.id).where(*base))).scalars().all()
        )
        if not ids:
            return 0
        await self._repo.session.execute(
            update(User)
            .where(User.id.in_(ids))
            .values(is_active=active, suspended_by_owner=not active)
        )
        if active:
            rows = (
                await self._repo.session.execute(
                    select(ClientAssignment).where(
                        ClientAssignment.user_id.in_(ids),
                        ClientAssignment.status == AssignmentStatus.DISABLED,
                    )
                )
            ).scalars().all()
            for a in rows:
                if (a.credentials or {}).get("ip_limited"):
                    continue
                a.status = AssignmentStatus.ACTIVE
        else:
            await self._repo.session.execute(
                update(ClientAssignment)
                .where(
                    ClientAssignment.user_id.in_(ids),
                    ClientAssignment.status == AssignmentStatus.ACTIVE,
                )
                .values(status=AssignmentStatus.DISABLED)
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
