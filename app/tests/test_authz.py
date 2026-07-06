from __future__ import annotations

import uuid

import pytest

from app.core.authz import Permission, authorize, has_permission, owner_scope
from app.core.exceptions import PermissionDeniedError
from app.domain.user import User, UserRole


def _admin(*, sudo: bool = False, modify: bool = True, uid: uuid.UUID | None = None) -> User:
    return User(
        id=uid or uuid.uuid4(),
        username="a",
        hashed_password="x",
        role=UserRole.ADMIN,
        is_sudo=sudo,
        modify_users_access=modify,
    )


def _enduser(*, owner_id: uuid.UUID | None = None) -> User:
    return User(
        id=uuid.uuid4(),
        username="u",
        hashed_password="x",
        role=UserRole.USER,
        owner_id=owner_id,
    )


def test_non_admin_has_no_admin_permissions():
    u = _enduser()
    for perm in Permission:
        assert has_permission(u, perm) is False


def test_admin_access_requires_admin_role():
    assert has_permission(_admin(), Permission.ADMIN_ACCESS) is True
    assert has_permission(_enduser(), Permission.ADMIN_ACCESS) is False


def test_sudo_permission():
    assert has_permission(_admin(sudo=True), Permission.SUDO) is True
    assert has_permission(_admin(sudo=False), Permission.SUDO) is False


def test_write_users_permission():
    assert has_permission(_admin(sudo=False, modify=True), Permission.WRITE_USERS) is True
    assert has_permission(_admin(sudo=True, modify=False), Permission.WRITE_USERS) is True
    assert has_permission(_admin(sudo=False, modify=False), Permission.WRITE_USERS) is False


def test_manage_user_sudo_bypasses_scope():
    sudo = _admin(sudo=True)
    assert has_permission(sudo, Permission.MANAGE_USER, target=_enduser()) is True


def test_manage_user_scoped_by_owner():
    admin = _admin(sudo=False)
    owned = _enduser(owner_id=admin.id)
    other = _enduser(owner_id=uuid.uuid4())
    assert has_permission(admin, Permission.MANAGE_USER, target=owned) is True
    assert has_permission(admin, Permission.MANAGE_USER, target=other) is False


def test_manage_user_without_target_denied_for_non_sudo():
    assert has_permission(_admin(sudo=False), Permission.MANAGE_USER) is False


def test_authorize_raises_with_codes():
    admin = _admin(sudo=False, modify=False)
    with pytest.raises(PermissionDeniedError) as ei:
        authorize(admin, Permission.SUDO)
    assert ei.value.code == "sudo_required"

    with pytest.raises(PermissionDeniedError) as ei:
        authorize(admin, Permission.WRITE_USERS)
    assert ei.value.code == "read_only_admin"

    with pytest.raises(PermissionDeniedError) as ei:
        authorize(admin, Permission.MANAGE_USER, target=_enduser(owner_id=uuid.uuid4()))
    assert ei.value.code == "user_out_of_scope"


def test_authorize_passes_when_allowed():
    authorize(_admin(sudo=True), Permission.SUDO)
    authorize(_admin(sudo=True), Permission.MANAGE_USER, target=_enduser())


def test_owner_scope():
    admin = _admin(sudo=False)
    assert owner_scope(admin) == admin.id
    assert owner_scope(_admin(sudo=True)) is None
