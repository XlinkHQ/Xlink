"""bulk_action mutates up to 1000 users per call and its whole body was
untested. The contract that matters: each user is isolated (one failure must
not roll back the rest), scope is enforced per user, and the counters are
honest."""

from __future__ import annotations

import uuid

import pytest

from app.core.security import hash_password
from app.domain.user import DataResetStrategy, User, UserRole
from app.repositories.user import UserRepository
from app.services.user_bulk_service import UserBulkService


def _user(username: str, *, owner_id: uuid.UUID | None = None, **kw) -> User:
    return User(
        username=username,
        hashed_password=hash_password("bulk-test-password-1234-AB!"),
        role=UserRole.USER,
        is_active=True,
        owner_id=owner_id,
        **kw,
    )


@pytest.fixture
async def ctx(app_state):
    """A real session + cache, a sudo admin, and three plain users."""
    async with app_state.db.session() as session:
        admin = User(
            username="root",
            hashed_password=hash_password("sudo-password-1234-AB!"),
            role=UserRole.ADMIN,
            is_sudo=True,
        )
        session.add(admin)
        users = [_user(f"u{i}") for i in range(3)]
        for u in users:
            session.add(u)
        await session.flush()

        svc = UserBulkService(UserRepository(session), app_state.cache)
        yield svc, session, admin, users


async def test_disable_marks_every_target(ctx) -> None:
    svc, session, admin, users = ctx
    ids = [u.id for u in users]

    result = await svc.bulk_action("disable", ids, admin=admin)

    assert result == {"ok": 3, "failed": 0}
    for u in users:
        await session.refresh(u)
        assert u.is_active is False


async def test_enable_reverses_disable(ctx) -> None:
    svc, session, admin, users = ctx
    ids = [u.id for u in users]
    await svc.bulk_action("disable", ids, admin=admin)

    result = await svc.bulk_action("enable", ids, admin=admin)

    assert result == {"ok": 3, "failed": 0}
    for u in users:
        await session.refresh(u)
        assert u.is_active is True


async def test_delete_is_soft(ctx) -> None:
    svc, session, admin, users = ctx

    result = await svc.bulk_action("delete", [u.id for u in users], admin=admin)

    assert result["ok"] == 3
    for u in users:
        await session.refresh(u)
        assert u.removed is True
        assert u.is_active is False


async def test_set_data_limit_applies_to_all(ctx) -> None:
    svc, session, admin, users = ctx

    result = await svc.bulk_action(
        "set_data_limit", [u.id for u in users], admin=admin, data_limit_bytes=5_000
    )

    assert result["ok"] == 3
    for u in users:
        await session.refresh(u)
        assert u.data_limit_bytes == 5_000


async def test_set_expiry_and_extend_expiry(ctx) -> None:
    from datetime import UTC, datetime, timedelta

    svc, session, admin, users = ctx
    when = datetime.now(UTC) + timedelta(days=10)

    await svc.bulk_action("set_expiry", [u.id for u in users], admin=admin, expire_at=when)
    for u in users:
        await session.refresh(u)
        assert u.expire_at is not None

    before = [u.expire_at for u in users]
    await svc.bulk_action("extend_expiry", [u.id for u in users], admin=admin, extend_days=5)
    for u, prev in zip(users, before, strict=True):
        await session.refresh(u)
        assert u.expire_at > prev


async def test_set_reset_strategy(ctx) -> None:
    svc, session, admin, users = ctx

    result = await svc.bulk_action(
        "set_reset_strategy", [u.id for u in users], admin=admin, data_reset_strategy="month"
    )

    assert result["ok"] == 3
    for u in users:
        await session.refresh(u)
        assert u.data_reset_strategy is DataResetStrategy.MONTH


# --------------------------------------------------------------------------
# The isolation contract — the reason the loop opens a savepoint per user
# --------------------------------------------------------------------------


async def test_one_missing_user_does_not_stop_the_others(ctx) -> None:
    svc, session, admin, users = ctx
    ids = [users[0].id, uuid.uuid4(), users[1].id]  # middle id does not exist

    result = await svc.bulk_action("disable", ids, admin=admin)

    assert result == {"ok": 2, "failed": 1}
    await session.refresh(users[0])
    await session.refresh(users[1])
    assert users[0].is_active is False
    assert users[1].is_active is False


async def test_out_of_scope_user_is_skipped_not_fatal(app_state) -> None:
    """A non-sudo admin may only touch users it owns; the rest must be counted
    as failed while its own users still go through."""
    async with app_state.db.session() as session:
        reseller = User(
            username="reseller",
            hashed_password=hash_password("reseller-password-1234-AB!"),
            role=UserRole.ADMIN,
            is_sudo=False,
        )
        session.add(reseller)
        await session.flush()

        mine = _user("mine", owner_id=reseller.id)
        theirs = _user("theirs")  # no owner -> out of this admin's scope
        session.add(mine)
        session.add(theirs)
        await session.flush()

        svc = UserBulkService(UserRepository(session), app_state.cache)
        result = await svc.bulk_action("disable", [mine.id, theirs.id], admin=reseller)

        assert result == {"ok": 1, "failed": 1}
        await session.refresh(mine)
        await session.refresh(theirs)
        assert mine.is_active is False
        assert theirs.is_active is True  # untouched


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


async def test_unknown_action_fails_every_user_rather_than_raising(ctx) -> None:
    svc, _session, admin, users = ctx

    result = await svc.bulk_action("not_an_action", [u.id for u in users], admin=admin)

    assert result == {"ok": 0, "failed": 3}


async def test_invalid_reset_strategy_is_rejected_upfront(ctx) -> None:
    from app.core.exceptions import ValidationError

    svc, _session, admin, users = ctx
    with pytest.raises(ValidationError):
        await svc.bulk_action(
            "set_reset_strategy",
            [u.id for u in users],
            admin=admin,
            data_reset_strategy="fortnightly",
        )


async def test_extend_expiry_requires_days(ctx) -> None:
    from app.core.exceptions import ValidationError

    svc, _session, admin, users = ctx
    with pytest.raises(ValidationError):
        await svc.bulk_action("extend_expiry", [u.id for u in users], admin=admin)


async def test_empty_id_list_is_a_no_op(ctx) -> None:
    svc, _session, admin, _users = ctx
    assert await svc.bulk_action("disable", [], admin=admin) == {"ok": 0, "failed": 0}


async def test_reset_usage_zeroes_the_counter(ctx) -> None:
    svc, session, admin, users = ctx
    users[0].users_data_usage = 12_345
    await session.flush()

    result = await svc.bulk_action("reset_usage", [users[0].id], admin=admin)

    assert result["ok"] == 1
    await session.refresh(users[0])
    assert users[0].users_data_usage == 0
