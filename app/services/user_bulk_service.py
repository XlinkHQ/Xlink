from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from app.core.exceptions import ValidationError
from app.domain.user import User
from app.services.user_service import UserService
from app.services.user_service_base import UserServiceBase, logger


class UserBulkService(UserServiceBase):
    @property
    def _core(self) -> UserService:
        return UserService(self._repo, self._cache, self._webhooks, self._subscription_service)

    async def bulk_action(
        self,
        action: str,
        user_ids: Sequence[uuid.UUID],
        *,
        admin: User,
        data_limit_bytes: int | None = None,
        expire_at: datetime | None = None,
        extend_days: int | None = None,
        data_reset_strategy: str | None = None,
    ) -> dict[str, int]:
        from datetime import UTC, datetime, timedelta

        from app.domain.user import DataResetStrategy

        core = self._core
        strategy_value: DataResetStrategy | None = None
        if action == "set_reset_strategy":
            try:
                strategy_value = DataResetStrategy(data_reset_strategy or "no_reset")
            except ValueError as exc:
                raise ValidationError(
                    "Invalid reset strategy.", code="invalid_reset_strategy"
                ) from exc
        if action == "extend_expiry" and not extend_days:
            raise ValidationError("extend_days is required.", code="extend_days_required")
        limit_value = data_limit_bytes or None

        ok = 0
        failed = 0
        for uid in user_ids:
            try:
                async with self._repo.session.begin_nested():
                    target = await self.get(uid)
                    self.assert_can_manage(admin, target)
                    if action == "enable":
                        await core.enable(uid)
                    elif action == "disable":
                        await core.disable(uid)
                    elif action == "delete":
                        await core.delete(uid)
                    elif action == "reset_usage":
                        await self._reset_user_usage(uid)
                    elif action == "set_data_limit":
                        if (
                            limit_value is not None
                            and target.owner_id is not None
                            and limit_value > (target.data_limit_bytes or 0)
                        ):
                            await self._enforce_owner_quota(
                                target.owner_id,
                                limit_value,
                                old_limit_bytes=target.data_limit_bytes,
                                is_update=True,
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
                    if action in ("set_data_limit", "set_expiry", "extend_expiry"):
                        refreshed = await self.get(uid)
                        await self._repo.session.refresh(refreshed, ["users_data_usage"])
                        await self._reactivate_recovered(refreshed)
                if action in (
                    "set_data_limit",
                    "set_expiry",
                    "extend_expiry",
                    "set_reset_strategy",
                ):
                    await self._invalidate(uid)
                if action in ("set_data_limit", "set_expiry", "extend_expiry"):
                    await self._invalidate_user_feed(uid)
                ok += 1
            except Exception as exc:
                logger.warning("bulk_action_skip", action=action, user_id=str(uid), error=str(exc))
                failed += 1
        return {"ok": ok, "failed": failed}

    async def _reset_user_usage(self, user_id: uuid.UUID) -> None:
        from app.traffic.service import TrafficService

        await TrafficService(self._repo.session, cache=self._cache).reset_user(user_id)
