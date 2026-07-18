from __future__ import annotations

import shlex
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import XLinkError
from app.db.redis import RedisCache
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.group import Group
from app.domain.node import Node, NodeStatus
from app.domain.profile import Profile
from app.domain.user import User, UserRole
from app.repositories.node import NodeRepository
from app.repositories.user import UserRepository
from app.schemas.node import NodeCreate
from app.schemas.user import UserCreate, UserUpdate
from app.services.admin_service import AdminService
from app.services.node_service import NodeService
from app.services.user_service import UserService
from app.services.user_totp_service import UserTotpService
from app.subscription.schemas import FeedScope
from app.subscription.tokens import create_subscription_token
from app.webhooks.dispatcher import WebhookDispatcher

GIB = 1024**3


class CliError(Exception):
    pass


def _opts(tokens: list[str]) -> tuple[list[str], dict[str, str], set[str]]:
    pos: list[str] = []
    kv: dict[str, str] = {}
    flags: set[str] = set()
    i = 0
    aliases = {
        "-u": "username",
        "-p": "password",
        "-n": "name",
        "-s": "search",
        "-l": "limit",
        "-f": "format",
    }
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("-"):
            key = aliases.get(tok, tok.lstrip("-"))
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                kv[key] = tokens[i + 1]
                i += 2
            else:
                flags.add(key)
                i += 1
        else:
            pos.append(tok)
            i += 1
    return pos, kv, flags


def _table(headers: list[str], rows: list[list[str]]) -> str:

    head = [h.upper() for h in headers]
    widths = [len(h) for h in head]
    for row in rows:
        for j, cell in enumerate(row):
            widths[j] = max(widths[j], len(str(cell)))
    sep = "  "
    out = [sep.join(h.ljust(widths[j]) for j, h in enumerate(head))]
    out.append(sep.join("─" * widths[j] for j in range(len(head))))
    if rows:
        out.extend(
            sep.join(str(c).ljust(widths[j]) for j, c in enumerate(row)) for row in rows
        )
    else:
        out.append("(none)")
    return "\n".join(out)


def _gib(b: int | None) -> str:
    return "∞" if not b else f"{b / GIB:.1f}G"


HELP = """
  XLink CLI · admin command-line for the panel
  Usage: xlink <group> <command> [options]

ADMINS
  admin list                         list admins (with sudo flag)
  admin create -u USER [-p PASS] [--no-sudo]   create admin (env: XLINK_ADMIN_PASSWORD)
  admin update -u USER [-p PASS] [--sudo|--no-sudo]
  admin reset-password -u USER -p PASS   reset password + re-enable (lockout recovery)
  admin import-from-env              create/update sudo admin from XLINK_ADMIN_* env
  admin delete -u USER --yes         delete an admin (--yes required)

USERS
  user list [--status S] [-s TEXT] [--owner ADMIN]   list VPN users
  user show -u USER                  user detail + subscription link
  user create -u USER [--limit GIB] [--expire YYYY-MM-DD]
  user delete -u USER --yes          (--yes required)
  user disable -u USER               |  user enable -u USER
  user set-limit -u USER --limit GIB |  user set-expire -u USER --expire YYYY-MM-DD
  user reset-usage -u USER           |  user revoke-sub -u USER
  user set-owner -u USER --owner ADMIN [--yes]

NODES
  node list                          list nodes
  node create -n NAME --host HOST [--port 443]
  node token NAME                    issue an agent token (shown once)
  node delete NAME

SERVICES & SUBSCRIPTION
  profile list                       |  group list
  sub link -u USER                   subscription URL
  sub config -u USER [-f FORMAT]     render the config (links|base64|clash|singbox|xray)

SYSTEM
  system stats                       node / user / traffic totals
  help                               show this help"""


async def run_cli(
    session: AsyncSession,
    cache: RedisCache,
    settings: Settings,
    command: str,
) -> str:
    try:
        tokens = shlex.split(command.strip())
    except ValueError as exc:
        return f"parse error: {exc}"
    if not tokens:
        return ""
    group, *rest = tokens
    try:
        handler = _DISPATCH.get(group)
        if handler is None:
            return f"unknown command '{group}'. Type 'help'."
        return await handler(session, cache, settings, rest)
    except CliError as exc:
        await session.rollback()
        return f"error: {exc}"
    except XLinkError as exc:
        await session.rollback()
        return f"error: {exc.message}"
    except PydanticValidationError as exc:
        await session.rollback()
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", ())) or "input"
        return f"error: invalid {field} — {first.get('msg', 'validation failed')}"
    except Exception as exc:
        await session.rollback()
        return f"error: {type(exc).__name__}: {exc}"


def _need(kv: dict[str, str], key: str) -> str:
    if key not in kv or not kv[key]:
        raise CliError(f"--{key} is required")
    return kv[key]


async def _find_user(session: AsyncSession, username: str, *, admin: bool = False) -> User:
    repo = UserRepository(session)
    user = await repo.get_by_username(username)
    if (
        user is None
        or (admin and user.role is not UserRole.ADMIN)
        or (not admin and user.role is UserRole.ADMIN)
    ):
        raise CliError(f"{'admin' if admin else 'user'} '{username}' not found")
    return user


async def _admin(session, cache, settings, rest):
    sub, *args = rest or ["list"]
    _, kv, flags = _opts(args)
    repo = UserRepository(session)
    disp = WebhookDispatcher(settings)
    svc = UserService(repo, cache, disp)
    admin_svc = AdminService(repo, cache, disp)
    totp_svc = UserTotpService(repo, cache, disp)
    if sub == "list":
        rows = (
            (await session.execute(select(User).where(User.role == UserRole.ADMIN))).scalars().all()
        )
        return (
            _table(
                ["username", "sudo", "active", "email"],
                [
                    [
                        a.username,
                        "yes" if a.is_sudo else "no",
                        "yes" if a.is_active else "no",
                        a.email or "—",
                    ]
                    for a in rows
                ],
            )
            or "no admins"
        )
    if sub == "create":
        password = kv.get("password") or (
            settings.admin_password.get_secret_value() if settings.admin_password else None
        )
        if not password:
            raise CliError("--password is required (or set XLINK_ADMIN_PASSWORD)")

        is_sudo = not ("no-sudo" in flags or "reseller" in flags)
        user = await admin_svc.create_admin(
            UserCreate(username=_need(kv, "username"), password=password, is_sudo=is_sudo)
        )
        await session.commit()
        return f"admin '{user.username}' created ({'sudo' if is_sudo else 'reseller'})."
    if sub == "update":
        admin = await _find_user(session, _need(kv, "username"), admin=True)
        if kv.get("password"):
            from app.core.security import hash_password

            await totp_svc.update_password_hash(admin, hash_password(kv["password"]))
        if "sudo" in flags:
            admin.is_sudo = True
        elif "no-sudo" in flags:
            admin.is_sudo = False
        await session.commit()
        return f"admin '{admin.username}' updated."
    if sub == "reset-password":
        admin = await _find_user(session, _need(kv, "username"), admin=True)
        from app.core.security import hash_password

        admin.is_active = True
        await totp_svc.update_password_hash(admin, hash_password(_need(kv, "password")))
        await session.commit()
        return f"admin '{admin.username}' password reset and re-enabled."
    if sub == "import-from-env":
        if not (settings.admin_username and settings.admin_password):
            raise CliError("XLINK_ADMIN_USERNAME / XLINK_ADMIN_PASSWORD are not set")
        existing = await UserRepository(session).get_by_username(settings.admin_username)
        if existing is not None:
            from app.core.security import hash_password

            existing.is_sudo = True
            await totp_svc.update_password_hash(
                existing, hash_password(settings.admin_password.get_secret_value())
            )
            await session.commit()
            return f"admin '{existing.username}' updated from env."
        user = await admin_svc.create_admin(
            UserCreate(
                username=settings.admin_username,
                password=settings.admin_password.get_secret_value(),
                is_sudo=True,
            )
        )
        await session.commit()
        return f"admin '{user.username}' created from env."
    if sub == "delete":
        admin = await _find_user(session, _need(kv, "username"), admin=True)
        if "yes" not in flags:
            return f"refusing to delete admin '{admin.username}' — pass --yes to confirm."
        await svc.delete(admin.id)
        await session.commit()
        return f"admin '{admin.username}' deleted."
    raise CliError(f"unknown 'admin {sub}'")


_USER_TARGET_SUBS = frozenset(
    {
        "set-owner",
        "delete",
        "disable",
        "enable",
        "reset-usage",
        "revoke-sub",
        "set-limit",
        "set-expire",
    }
)


async def _user(session, cache, settings, rest):
    sub, *args = rest or ["list"]
    _, kv, flags = _opts(args)
    svc = UserService(UserRepository(session), cache, WebhookDispatcher(settings))

    if sub == "list":
        stmt = select(User).where(User.role == UserRole.USER)
        if kv.get("status") == "active":
            stmt = stmt.where(User.is_active.is_(True))
        elif kv.get("status") == "disabled":
            stmt = stmt.where(User.is_active.is_(False))
        if kv.get("search"):
            stmt = stmt.where(User.username.ilike(f"%{kv['search']}%"))
        if kv.get("owner"):
            owner = await _find_user(session, kv["owner"], admin=True)
            stmt = stmt.where(User.owner_id == owner.id)
        stmt = stmt.limit(int(kv.get("limit", 100)))
        rows = (await session.execute(stmt)).scalars().all()
        return (
            _table(
                ["username", "status", "limit", "expire"],
                [
                    [
                        u.username,
                        "active" if u.is_active else "disabled",
                        _gib(u.data_limit_bytes),
                        u.expire_at.strftime("%Y-%m-%d") if u.expire_at else "never",
                    ]
                    for u in rows
                ],
            )
            or "no users"
        )

    if sub == "show":
        u = await _find_user(session, _need(kv, "username"))
        used = int(
            await session.scalar(
                select(func.coalesce(func.sum(ClientAssignment.used_bytes), 0)).where(
                    ClientAssignment.user_id == u.id,
                    ClientAssignment.status == AssignmentStatus.ACTIVE,
                )
            )
            or 0
        )
        token = create_subscription_token(u.id, FeedScope.USER, settings, revision=u.sub_revision)
        url = f"{settings.api_v1_prefix!s}/subscriptions/sub/{token}"
        return "\n".join(
            [
                f"username : {u.username}",
                f"status   : {'active' if u.is_active else 'disabled'}",
                f"usage    : {_gib(used)} / {_gib(u.data_limit_bytes)}",
                f"expire   : {u.expire_at.strftime('%Y-%m-%d') if u.expire_at else 'never'}",
                f"sub link : {url}",
            ]
        )

    if sub == "create":
        limit = int(float(kv["limit"]) * GIB) if kv.get("limit") else None
        expire = (
            datetime.strptime(kv["expire"], "%Y-%m-%d").replace(tzinfo=UTC)
            if kv.get("expire")
            else None
        )
        u = await svc.create(
            UserCreate(username=_need(kv, "username"), data_limit_bytes=limit, expire_at=expire)
        )
        await session.commit()
        return f"user '{u.username}' created."

    if sub not in _USER_TARGET_SUBS:
        raise CliError(f"unknown 'user {sub}'")
    u = await _find_user(session, _need(kv, "username"))
    if sub == "set-owner":
        owner = await _find_user(session, _need(kv, "owner"), admin=True)
        if u.owner_id is not None and u.owner_id != owner.id and "yes" not in flags:
            current = await session.get(User, u.owner_id)
            cur_name = current.username if current else str(u.owner_id)
            return (
                f"'{u.username}' is already owned by '{cur_name}'. "
                f"Pass --yes to transfer ownership to '{owner.username}'."
            )
        u.owner_id = owner.id
        await session.commit()
        return f"'{u.username}' owner set to '{owner.username}'."
    if sub == "delete":
        if "yes" not in flags:
            return f"refusing to delete user '{u.username}' — pass --yes to confirm."
        await svc.delete(u.id)
        await session.commit()
        return f"user '{u.username}' deleted."
    if sub == "disable":
        await svc.disable(u.id)
        await session.commit()
        return f"user '{u.username}' disabled."
    if sub == "enable":
        await svc.enable(u.id)
        await session.commit()
        return f"user '{u.username}' enabled."
    if sub == "reset-usage":
        from app.traffic.repository import TrafficRepository

        n = await TrafficRepository(session).reset_for_user(u.id)
        await session.commit()
        return f"reset usage on {n} assignment(s)."
    if sub == "revoke-sub":
        await svc.revoke_subscription(u.id)
        await session.commit()
        return "subscription revoked."
    if sub == "set-limit":
        limit = int(float(_need(kv, "limit")) * GIB)
        await svc.update_quota(u.id, UserUpdate(data_limit_bytes=limit, expire_at=u.expire_at))
        await session.commit()
        return f"limit set to {_gib(limit)}."
    if sub == "set-expire":
        expire = datetime.strptime(_need(kv, "expire"), "%Y-%m-%d").replace(tzinfo=UTC)
        await svc.update_quota(
            u.id, UserUpdate(data_limit_bytes=u.data_limit_bytes, expire_at=expire)
        )
        await session.commit()
        return f"expire set to {kv['expire']}."
    raise CliError(f"unknown 'user {sub}'")


async def _node(session, cache, settings, rest):
    sub, *args = rest or ["list"]
    pos, kv, _ = _opts(args)
    svc = NodeService(NodeRepository(session))

    if sub == "list":
        rows = (await session.execute(select(Node))).scalars().all()
        return (
            _table(
                ["name", "host", "port", "status", "users"],
                [[n.name, n.host, str(n.port), n.status.value, str(n.current_users)] for n in rows],
            )
            or "no nodes"
        )
    if sub == "create":
        name = _need(kv, "name")
        node = await svc.create(
            NodeCreate(
                name=name,
                slug=name.lower().replace(" ", "-"),
                host=_need(kv, "host"),
                port=int(kv.get("port", 443)),
                max_users=1_000_000,
            )
        )
        await session.commit()
        return f"node '{node.name}' created (id {node.id})."

    name = pos[0] if pos else _need(kv, "name")
    node = (await session.execute(select(Node).where(Node.name == name))).scalar()
    if node is None:
        raise CliError(f"node '{name}' not found")
    if sub == "token":
        token = await svc.provision_agent_token(node.id)
        await session.commit()
        return f"node id : {node.id}\nagent token (shown once): {token}"
    if sub == "delete":
        await svc.delete(node.id)
        await session.commit()
        return f"node '{node.name}' deleted."
    raise CliError(f"unknown 'node {sub}'")


async def _profile(session, cache, settings, rest):
    rows = (await session.execute(select(Profile))).scalars().all()
    return (
        _table(
            ["name", "provider", "protocol"],
            [[p.name, p.provider_kind.value, p.protocol] for p in rows],
        )
        or "no profiles"
    )


async def _group(session, cache, settings, rest):
    rows = (await session.execute(select(Group))).scalars().all()
    return (
        _table(
            ["name", "slug", "inbounds"], [[g.name, g.slug, str(len(g.profile_ids))] for g in rows]
        )
        or "no groups"
    )


_SUB_FORMAT_ALIASES = {
    "links": "text",
    "text": "text",
    "base64": "base64",
    "v2ray": "base64",
    "clash": "clash_yaml",
    "clash-meta": "mihomo_yaml",
    "mihomo": "mihomo_yaml",
    "singbox": "singbox_json",
    "sing-box": "singbox_json",
    "xray": "xray_json",
}


async def _sub(session, cache, settings, rest):
    sub, *args = rest or ["link"]
    _, kv, _ = _opts(args)
    u = await _find_user(session, _need(kv, "username"))
    token = create_subscription_token(u.id, FeedScope.USER, settings, revision=u.sub_revision)
    if sub == "link":
        return f"{settings.api_v1_prefix}/subscriptions/sub/{token}"
    if sub in ("config", "get-config"):
        from app.providers.discovery import build_registry
        from app.subscription.generator import SubscriptionGenerator
        from app.subscription.renderer import SubscriptionRenderer
        from app.subscription.repository import SubscriptionRepository
        from app.subscription.schemas import FeedRequest, RenderVersion, SubscriptionFormat
        from app.subscription.service import SubscriptionService

        fmt_key = _SUB_FORMAT_ALIASES.get((kv.get("format") or "links").lower(), "text")
        svc = SubscriptionService(
            SubscriptionRepository(session),
            SubscriptionGenerator(build_registry()),
            SubscriptionRenderer(),
            cache,
        )
        feed = await svc.feed(
            FeedRequest(
                scope=FeedScope.USER,
                subject_id=u.id,
                format=SubscriptionFormat(fmt_key),
                version=RenderVersion.V1,
                use_cache=False,
            )
        )
        return feed.content or "(empty subscription)"
    raise CliError("usage: sub link|config -u USER [-f FORMAT]")


async def _system(session, cache, settings, rest):
    async def count(stmt) -> int:
        return int(await session.scalar(stmt) or 0)

    nodes = await count(select(func.count()).select_from(Node))
    nodes_active = await count(
        select(func.count()).select_from(Node).where(Node.status == NodeStatus.ACTIVE)
    )
    nodes_off = nodes - nodes_active
    users = await count(select(func.count()).select_from(User).where(User.role == UserRole.USER))
    users_active = await count(
        select(func.count())
        .select_from(User)
        .where(User.role == UserRole.USER, User.is_active.is_(True))
    )
    admins = await count(select(func.count()).select_from(User).where(User.role == UserRole.ADMIN))
    asn = await count(
        select(func.count())
        .select_from(ClientAssignment)
        .where(ClientAssignment.status == AssignmentStatus.ACTIVE)
    )
    profiles = await count(select(func.count()).select_from(Profile))
    groups = await count(select(func.count()).select_from(Group))
    traffic = await count(select(func.coalesce(func.sum(ClientAssignment.used_bytes), 0)))

    return "\n".join(
        [
            f"nodes        {nodes_active} active, {nodes_off} offline, {nodes} total",
            f"users        {users_active} active, {users - users_active} disabled, {users} total",
            f"admins       {admins}",
            f"assignments  {asn} active",
            f"profiles     {profiles}",
            f"groups       {groups}",
            f"traffic      {_gib(traffic)} total",
        ]
    )


async def _help(session, cache, settings, rest):
    return HELP


_DISPATCH: dict[str, Any] = {
    "admin": _admin,
    "user": _user,
    "node": _node,
    "profile": _profile,
    "group": _group,
    "sub": _sub,
    "subscription": _sub,
    "system": _system,
    "help": _help,
}
