"""Role-based access control for non-sudo admins.

Model (after PasarGuard's admin roles): a role grants, per resource and action,
a scope — NONE (denied), OWN (only users this admin owns) or ALL. An action
absent from the role is denied. A role also carries limits that bound what the
admin may grant (user count, data limit, expiry).

Compatibility is the hard requirement: sudo admins are unaffected, and an admin
with no role keeps exactly the legacy behaviour (owner-scoped user management,
gated by `modify_users_access`). Roles only take effect once assigned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any

from app.core.exceptions import PermissionDeniedError, ValidationError


class Scope(IntEnum):
    NONE = 0
    OWN = 1
    ALL = 2


# The catalogue every role is validated against. Keeping it explicit means a
# typo in a stored role ("delte") is rejected at save time rather than silently
# denying forever.
CATALOGUE: dict[str, frozenset[str]] = {
    "users": frozenset(
        {
            "create",
            "read",
            "update",
            "delete",
            "disable",
            "reset_usage",
            "revoke_sub",
            "bulk",
            "devices",
        }
    ),
}

# Every users.* action that mutates state (everything except read).
WRITE_ACTIONS = CATALOGUE["users"] - {"read"}

LIMIT_KEYS = frozenset({"max_users", "data_limit_min", "data_limit_max", "expire_max_days"})


@dataclass(frozen=True, slots=True)
class RolePolicy:
    """A role resolved for one request, attached to the acting user."""

    name: str
    permissions: dict[str, dict[str, int]] = field(default_factory=dict)
    limits: dict[str, int] = field(default_factory=dict)

    def scope(self, resource: str, action: str) -> Scope:
        raw = self.permissions.get(resource, {}).get(action, 0)
        try:
            return Scope(int(raw))
        except (TypeError, ValueError):
            return Scope.NONE


def policy_of(actor: Any) -> RolePolicy | None:
    return getattr(actor, "rbac_policy", None)


def effective_scope(actor: Any, resource: str, action: str) -> Scope:
    """What the actor may do. Sudo is ALL; no role falls back to legacy rules."""
    if getattr(actor, "is_sudo", False):
        return Scope.ALL
    if not getattr(actor, "is_admin", False):
        return Scope.NONE
    policy = policy_of(actor)
    if policy is None:
        # Legacy: non-sudo admins manage their own users; writes need the flag.
        if resource == "users":
            if action == "read":
                return Scope.OWN
            return Scope.OWN if getattr(actor, "modify_users_access", False) else Scope.NONE
        return Scope.NONE
    return policy.scope(resource, action)


def require(actor: Any, resource: str, action: str, *, target: Any = None) -> Scope:
    """Raise unless the actor may perform `action`, against `target` if given."""
    scope = effective_scope(actor, resource, action)
    if scope is Scope.NONE:
        raise PermissionDeniedError(
            f"Your role does not allow {resource}.{action}.", code="role_forbidden"
        )
    if (
        target is not None
        and scope is Scope.OWN
        and getattr(target, "owner_id", None) != getattr(actor, "id", None)
    ):
        raise PermissionDeniedError("This user is not in your scope.", code="user_out_of_scope")
    return scope


# ------------------------------------------------------------------ limits
def enforce_limits(
    actor: Any,
    *,
    data_limit_bytes: int | None = None,
    expire_at: datetime | None = None,
    owned_user_count: int | None = None,
    creating: bool = False,
) -> None:
    """Bound what a role-holding admin may grant. Sudo and role-less admins are
    governed by the existing quota fields instead."""
    if getattr(actor, "is_sudo", False):
        return
    policy = policy_of(actor)
    if policy is None or not policy.limits:
        return
    lim = policy.limits
    if (
        creating
        and owned_user_count is not None
        and lim.get("max_users") is not None
        and owned_user_count >= int(lim["max_users"])
    ):
        raise ValidationError(
            f"Your role allows at most {lim['max_users']} users.", code="role_max_users"
        )
    if data_limit_bytes is not None:
        lo, hi = lim.get("data_limit_min"), lim.get("data_limit_max")
        if lo is not None and data_limit_bytes < int(lo):
            raise ValidationError(
                "Data limit is below your role's minimum.", code="role_data_limit"
            )
        if hi is not None and data_limit_bytes > int(hi):
            raise ValidationError(
                "Data limit is above your role's maximum.", code="role_data_limit"
            )
    elif creating and lim.get("data_limit_max") is not None:
        # An unlimited user would escape the role's ceiling entirely.
        raise ValidationError(
            "Your role requires a data limit on every user.", code="role_data_limit"
        )
    if lim.get("expire_max_days") is not None:
        from datetime import UTC, timedelta

        ceiling = datetime.now(UTC) + timedelta(days=int(lim["expire_max_days"]))
        if expire_at is None:
            if creating:
                raise ValidationError(
                    "Your role requires an expiry on every user.", code="role_expire"
                )
        else:
            exp = expire_at if expire_at.tzinfo else expire_at.replace(tzinfo=UTC)
            if exp > ceiling:
                raise ValidationError(
                    f"Expiry exceeds your role's {lim['expire_max_days']}-day maximum.",
                    code="role_expire",
                )


# ------------------------------------------------------------------ validation
def validate_role_payload(permissions: dict[str, Any], limits: dict[str, Any]) -> None:
    for resource, actions in permissions.items():
        if resource not in CATALOGUE:
            raise ValidationError(f"Unknown resource {resource!r}.", code="role_invalid")
        if not isinstance(actions, dict):
            raise ValidationError(f"{resource} must map actions to scopes.", code="role_invalid")
        for action, scope in actions.items():
            if action not in CATALOGUE[resource]:
                raise ValidationError(f"Unknown action {resource}.{action}.", code="role_invalid")
            if scope not in (0, 1, 2):
                raise ValidationError(
                    f"{resource}.{action}: scope must be 0 (none), 1 (own) or 2 (all).",
                    code="role_invalid",
                )
    for key, value in limits.items():
        if key not in LIMIT_KEYS:
            raise ValidationError(f"Unknown limit {key!r}.", code="role_invalid")
        if value is not None and (not isinstance(value, int) or value < 0):
            raise ValidationError(
                f"Limit {key} must be a non-negative integer.", code="role_invalid"
            )
    lo, hi = limits.get("data_limit_min"), limits.get("data_limit_max")
    if lo is not None and hi is not None and lo > hi:
        raise ValidationError("data_limit_min exceeds data_limit_max.", code="role_invalid")
