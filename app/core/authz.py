from __future__ import annotations

import uuid
from enum import StrEnum

from app.core.exceptions import PermissionDeniedError
from app.domain.user import User


class Permission(StrEnum):
    ADMIN_ACCESS = "admin_access"
    SUDO = "sudo"
    WRITE_USERS = "write_users"
    MANAGE_USER = "manage_user"
    MANAGE_INFRA = "manage_infra"


def has_permission(actor: User, permission: Permission, *, target: User | None = None) -> bool:
    if permission is Permission.ADMIN_ACCESS:
        return actor.is_admin
    if not actor.is_admin:
        return False
    if permission is Permission.SUDO:
        return actor.is_sudo
    if permission is Permission.MANAGE_INFRA:
        return actor.is_sudo
    if permission is Permission.WRITE_USERS:
        return actor.is_sudo or actor.modify_users_access
    if permission is Permission.MANAGE_USER:
        if actor.is_sudo:
            return True
        if target is not None:
            return target.owner_id == actor.id
        return False
    return False


_DENIALS = {
    Permission.ADMIN_ACCESS: ("Administrator access required.", None),
    Permission.SUDO: ("Sudo administrator access required.", "sudo_required"),
    Permission.MANAGE_INFRA: (
        "Infrastructure changes require a sudo administrator.",
        "sudo_required",
    ),
    Permission.WRITE_USERS: ("Read-only administrator.", "read_only_admin"),
    Permission.MANAGE_USER: ("This user is not in your scope.", "user_out_of_scope"),
}


def authorize(actor: User, permission: Permission, *, target: User | None = None) -> None:
    if not has_permission(actor, permission, target=target):
        message, code = _DENIALS[permission]
        if code is None:
            raise PermissionDeniedError(message)
        raise PermissionDeniedError(message, code=code)


def owner_scope(actor: User) -> uuid.UUID | None:
    return None if actor.is_sudo else actor.id


_SECRET_SETTING_MARKERS = (
    "private",
    "privatekey",
    "secret",
    "password",
    "presharedkey",
    "preshared",
    "uuid",
    "psk",
)
_PUBLIC_SETTING_KEYS = {"publickey", "pbk", "shortid", "sid", "spiderx"}


def _is_secret_setting(key: str) -> bool:
    k = key.lower().replace("_", "")
    if k in _PUBLIC_SETTING_KEYS:
        return False
    return any(m in k for m in _SECRET_SETTING_MARKERS)


def redact_settings(settings: dict, actor: User) -> dict:
    if actor.is_sudo or not isinstance(settings, dict):
        return settings
    return {k: ("***" if _is_secret_setting(k) else v) for k, v in settings.items()}


def assert_group_in_scope(
    actor: User, group_id: uuid.UUID | None, scoped_ids: set[uuid.UUID]
) -> None:
    if actor.is_sudo or actor.all_groups_access:
        return
    if group_id is None:
        raise PermissionDeniedError(
            "You may only assign users to your allowed groups.", code="group_out_of_scope"
        )
    if group_id not in scoped_ids:
        raise PermissionDeniedError("This group is not in your scope.", code="group_out_of_scope")
