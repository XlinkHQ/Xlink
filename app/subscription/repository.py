from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.client_assignment import ClientAssignment
from app.domain.node import Node
from app.domain.profile import Profile
from app.domain.user import User
from app.subscription.models import SubscriptionSource


@dataclass(frozen=True, slots=True)
class UserTrafficStats:
    used_bytes: int
    traffic_limit_bytes: int | None
    expire_timestamp: int | None
    upload_bytes: int = 0
    download_bytes: int = 0


class SubscriptionRepository:
    def __init__(
        self, session: AsyncSession, *, reader_session: AsyncSession | None = None
    ) -> None:
        self._session = session
        # OPTIONAL replica session for pure, lag-tolerant reads (subscription
        # SOURCE listings). None when no replica is configured → reads use the
        # primary session, identical to before. Never used for writes or for
        # read-after-write-sensitive paths (quota/traffic-stats/on-hold), which
        # stay on the primary session.
        self._reader = reader_session or session

    async def get_status_texts(self) -> dict[str, str] | None:
        from app.domain.app_settings import SINGLETON_ID, AppSettings

        row = await self._session.get(AppSettings, SINGLETON_ID)
        if row is None:
            return None
        return {
            "active": row.active_status_text,
            "expired": row.expired_status_text,
            "limited": row.limited_status_text,
            "disabled": row.disabled_status_text,
            "onhold": row.onhold_status_text,
            "remark": row.config_remark,
        }

    async def host_overrides(self, profile_ids):
        from app.repositories.inbound_host import InboundHostRepository

        return await InboundHostRepository(self._session).overrides_for_profiles(profile_ids)

    async def activate_on_hold(self, user_id: uuid.UUID) -> None:
        user = await self._session.get(User, user_id)
        if user is None or not user.on_hold:
            return
        now = datetime.now(UTC)

        deadline = user.activation_deadline
        if deadline is not None:
            dl = deadline if deadline.tzinfo else deadline.replace(tzinfo=UTC)
            if dl < now:
                user.expire_at = now
                user.on_hold = False
                # flush, not commit: the request-scoped session owns the
                # transaction and commits at the end (app/db/session.py).
                await self._session.flush()
                return
        if user.on_hold_duration_seconds:
            user.expire_at = now + timedelta(seconds=user.on_hold_duration_seconds)
        user.on_hold = False
        await self._session.flush()

    async def get_assignment_source(self, assignment_id: uuid.UUID) -> SubscriptionSource | None:
        rows = await self._sources(ClientAssignment.id == assignment_id)
        return rows[0] if rows else None

    async def list_assignment_sources(
        self, assignment_id: uuid.UUID
    ) -> tuple[SubscriptionSource, ...]:
        return await self._sources(ClientAssignment.id == assignment_id)

    async def list_profile_sources(self, profile_id: uuid.UUID) -> tuple[SubscriptionSource, ...]:
        return await self._sources(ClientAssignment.profile_id == profile_id)

    async def list_user_sources(self, user_id: uuid.UUID) -> tuple[SubscriptionSource, ...]:
        return await self._sources(ClientAssignment.user_id == user_id)

    async def pinned_node_ids(self, user_id: uuid.UUID) -> list:
        from app.domain.user import User

        value = await self._session.scalar(select(User.pinned_node_ids).where(User.id == user_id))
        return list(value) if value else []

    async def get_user_quota(self, user_id: uuid.UUID) -> UserTrafficStats:
        # Use the maintained account total (users_data_usage), NOT a sum over
        # ACTIVE assignments: once a user hits their limit their assignment flips
        # to LIMITED, so an ACTIVE-only sum reads 0 — the quota gate would then
        # think they're under limit and serve them a (filtered-empty) feed while
        # the status page shows "0 used / active". users_data_usage counts all
        # statuses, matching every enforcement path.
        user = await self._session.get(User, user_id)
        used = int(user.users_data_usage or 0) if user else 0
        limit = user.data_limit_bytes if user else None
        expire_ts = int(user.expire_at.timestamp()) if user and user.expire_at is not None else None
        return UserTrafficStats(
            used_bytes=used,
            traffic_limit_bytes=limit,
            expire_timestamp=expire_ts,
            upload_bytes=0,
            download_bytes=0,
        )

    async def get_user_traffic_stats(self, user_id: uuid.UUID) -> UserTrafficStats:
        from app.traffic.models import TrafficRecord

        up, down = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(TrafficRecord.upload_bytes), 0),
                    func.coalesce(func.sum(TrafficRecord.download_bytes), 0),
                )
                .select_from(TrafficRecord)
                .join(ClientAssignment, ClientAssignment.id == TrafficRecord.assignment_id)
                .where(
                    # All statuses (not ACTIVE-only): a LIMITED user's assignments
                    # aren't ACTIVE, so filtering would show up/down 0 while used>0.
                    ClientAssignment.user_id == user_id,
                )
            )
        ).one()

        user = await self._session.get(User, user_id)
        used = int(user.users_data_usage or 0) if user else 0
        limit = user.data_limit_bytes if user else None
        expire_ts = int(user.expire_at.timestamp()) if user and user.expire_at is not None else None
        return UserTrafficStats(
            used_bytes=used,
            traffic_limit_bytes=limit,
            expire_timestamp=expire_ts,
            upload_bytes=int(up),
            download_bytes=int(down),
        )

    async def _sources(self, *conditions) -> tuple[SubscriptionSource, ...]:
        from sqlalchemy.orm import selectinload

        stmt = (
            select(ClientAssignment, Profile, Node)
            .join(Profile, ClientAssignment.profile_id == Profile.id)
            .join(Node, ClientAssignment.node_id == Node.id)
            .options(selectinload(ClientAssignment.user))
            .where(*conditions)
            .order_by(ClientAssignment.created_at.desc(), ClientAssignment.id.desc())
        )
        # Pure read: safe to serve from the replica. selectinload issues its
        # follow-up SELECT on the SAME (reader) session, so the eager load stays
        # consistent within one snapshot.
        result = await self._reader.execute(stmt)
        return tuple(
            SubscriptionSource(assignment=assignment, profile=profile, node=node)
            for assignment, profile, node in result.all()
        )
