from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.services.user_service_base import UserServiceBase


class UserDeviceService(UserServiceBase):
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

        from app.domain.user import User
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
