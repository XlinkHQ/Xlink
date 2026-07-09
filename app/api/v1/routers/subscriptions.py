from __future__ import annotations

import base64
import re
import time
import uuid
from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response

from app.core.exceptions import AuthenticationError
from app.dependencies.auth import AdminUser, CurrentUser, SudoAdminUser
from app.dependencies.core import SettingsDep
from app.dependencies.services import (
    AssignmentServiceDep,
    SettingsServiceDep,
    SubscriptionServiceDep,
    UserServiceDep,
)
from app.subscription.page import render_custom_page, render_subscription_page

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.domain.user import User
    from app.services.user_service import UserService
from app.subscription.schemas import (
    ConfigRead,
    FeedRead,
    FeedRequest,
    FeedScope,
    RenderVersion,
    SubscriptionFormat,
)
from app.subscription.tokens import create_subscription_token, verify_subscription_token

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def _request(
    scope: FeedScope,
    subject_id: uuid.UUID,
    feed_format: SubscriptionFormat,
    version: RenderVersion,
    use_cache: bool,
) -> FeedRequest:
    return FeedRequest(
        scope=scope,
        subject_id=subject_id,
        format=feed_format,
        version=version,
        use_cache=use_cache,
    )


_FORMAT_CONTENT_TYPES: dict[SubscriptionFormat, str] = {
    SubscriptionFormat.SINGBOX_JSON: "application/json",
    SubscriptionFormat.XRAY_JSON: "application/json",
    SubscriptionFormat.CLASH_YAML: "text/yaml",
    SubscriptionFormat.MIHOMO_YAML: "text/yaml",
}


_UA_FORMAT_RULES: list[tuple[re.Pattern[str], SubscriptionFormat]] = [
    (
        re.compile(r"(?i)^(clash-verge|clash[-.]?meta|flclash|mihomo)"),
        SubscriptionFormat.MIHOMO_YAML,
    ),
    (re.compile(r"(?i)^(clash|stash)"), SubscriptionFormat.CLASH_YAML),
    (
        re.compile(r"(?i)^(SFA|SFI|SFM|SFT|karing|hiddifynext|sing-box)"),
        SubscriptionFormat.SINGBOX_JSON,
    ),
    (
        re.compile(r"(?i)^(v2box|nekoray|nekobox|hiddify)"),
        SubscriptionFormat.BASE64,
    ),
]


_RULE_RESULT_FORMATS: dict[str, SubscriptionFormat] = {
    "links": SubscriptionFormat.TEXT,
    "base64": SubscriptionFormat.BASE64,
    "xray": SubscriptionFormat.XRAY_JSON,
    "singbox": SubscriptionFormat.SINGBOX_JSON,
    "clash": SubscriptionFormat.CLASH_YAML,
    "clash-meta": SubscriptionFormat.MIHOMO_YAML,
}


class _BlockedSubscriptionError(Exception):
    pass


@lru_cache(maxsize=256)
def _compiled_rule(pattern: str) -> re.Pattern[str] | None:
    # Compile once per distinct pattern instead of re.match() recompiling on every
    # public-subscription hit (highest-traffic endpoint; up to 64 rules/request).
    try:
        return re.compile(pattern)
    except re.error:
        return None


def _match_admin_rules(user_agent: str, rules: list[dict[str, str]]) -> SubscriptionFormat | None:
    # Bound the ReDoS surface: admin patterns run against an attacker-controlled
    # User-Agent on a public endpoint. Cap both lengths so catastrophic
    # backtracking can't stall a worker.
    ua = user_agent[:512]
    for rule in rules:
        pattern = rule.get("pattern")
        result = rule.get("result")
        if not pattern or not result or len(pattern) > 256:
            continue
        rx = _compiled_rule(pattern)
        if rx is None:
            continue
        try:
            if rx.match(ua):
                if result == "block":
                    raise _BlockedSubscriptionError
                fmt = _RULE_RESULT_FORMATS.get(result)
                if fmt is not None:
                    return fmt
        except re.error:
            continue
    return None


_FORMAT_ALIASES: dict[str, SubscriptionFormat] = {
    "clash": SubscriptionFormat.CLASH_YAML,
    "clash-meta": SubscriptionFormat.MIHOMO_YAML,
    "mihomo": SubscriptionFormat.MIHOMO_YAML,
    "singbox": SubscriptionFormat.SINGBOX_JSON,
    "sing-box": SubscriptionFormat.SINGBOX_JSON,
    "v2ray": SubscriptionFormat.BASE64,
    "base64": SubscriptionFormat.BASE64,
    "text": SubscriptionFormat.TEXT,
    "xray": SubscriptionFormat.XRAY_JSON,
    "xray-json": SubscriptionFormat.XRAY_JSON,
    "json": SubscriptionFormat.XRAY_JSON,
}


_VPN_CLIENTS = (
    "clash",
    "stash",
    "mihomo",
    "flclash",
    "sing-box",
    "sfa",
    "sfi",
    "sfm",
    "sft",
    "v2ray",
    "v2box",
    "streisand",
    "nekoray",
    "nekobox",
    "hiddify",
    "karing",
    "loon",
    "quantumult",
    "surge",
    "shadowrocket",
)


def _is_browser(user_agent: str) -> bool:
    ua = user_agent.lower()
    return ua.startswith("mozilla") and not any(c in ua for c in _VPN_CLIENTS)


def _status_text(user: object, stats: object, cfg: object) -> tuple[str, str]:
    if not getattr(user, "is_active", True):
        return (cfg.disabled_status_text, "muted")
    if getattr(user, "on_hold", False):
        return (cfg.onhold_status_text, "warn")
    now = int(time.time())
    expire = getattr(stats, "expire_timestamp", None)
    limit = getattr(stats, "traffic_limit_bytes", None)
    used = getattr(stats, "used_bytes", 0)
    if expire is not None and expire < now:
        return (cfg.expired_status_text, "bad")
    if limit is not None and used >= limit:
        return (cfg.limited_status_text, "bad")
    return (cfg.active_status_text, "ok")


_VERSIONED_XRAY_CLIENTS: list[tuple[re.Pattern[str], tuple[int, ...]]] = [
    (re.compile(r"(?i)^v2rayNG/(\d+)\.(\d+)\.(\d+)"), (1, 8, 29)),
    (re.compile(r"(?i)^v2rayN/(\d+)\.(\d+)"), (6, 40)),
    (re.compile(r"(?i)^Happ/(\d+)\.(\d+)\.(\d+)"), (1, 63, 1)),
    (re.compile(r"(?i)^Streisand"), ()),
]


def _versioned_xray_format(user_agent: str) -> SubscriptionFormat | None:
    """Modern v2rayNG/v2rayN/Happ/Streisand support the richer xray-json feed."""
    for pattern, minimum in _VERSIONED_XRAY_CLIENTS:
        m = pattern.match(user_agent)
        if not m:
            continue
        if not minimum:
            return SubscriptionFormat.XRAY_JSON
        version = tuple(int(g) for g in m.groups())
        if version >= minimum:
            return SubscriptionFormat.XRAY_JSON
        return None
    return None


def _detect_format(
    user_agent: str,
    format_param: str | None,
    admin_rules: list[dict[str, str]] | None = None,
) -> SubscriptionFormat:
    if format_param is not None:
        lowered = format_param.strip().lower()
        if lowered in _FORMAT_ALIASES:
            return _FORMAT_ALIASES[lowered]

        try:
            return SubscriptionFormat(lowered)
        except ValueError:
            pass

    if admin_rules:
        matched = _match_admin_rules(user_agent, admin_rules)
        if matched is not None:
            return matched

    for pattern, fmt in _UA_FORMAT_RULES:
        if pattern.match(user_agent):
            return fmt

    versioned = _versioned_xray_format(user_agent)
    if versioned is not None:
        return versioned
    return SubscriptionFormat.BASE64


@router.get("/assignments/{assignment_id}/config", response_model=ConfigRead)
async def assignment_config(
    assignment_id: uuid.UUID,
    admin: AdminUser,
    subscriptions: SubscriptionServiceDep,
    assignments: AssignmentServiceDep,
    users: UserServiceDep,
) -> ConfigRead:
    assignment = await assignments.get(assignment_id)
    users.assert_can_manage(admin, await users.get(assignment.user_id))
    return await subscriptions.generate_config(assignment_id)


@router.get("/assignments/{assignment_id}/feed", response_model=FeedRead)
async def assignment_feed(
    assignment_id: uuid.UUID,
    admin: AdminUser,
    subscriptions: SubscriptionServiceDep,
    assignments: AssignmentServiceDep,
    users: UserServiceDep,
    format: SubscriptionFormat = SubscriptionFormat.TEXT,
    version: RenderVersion = RenderVersion.V1,
    use_cache: bool = True,
) -> FeedRead:
    assignment = await assignments.get(assignment_id)
    users.assert_can_manage(admin, await users.get(assignment.user_id))
    return await subscriptions.feed(
        _request(FeedScope.ASSIGNMENT, assignment_id, format, version, use_cache)
    )


@router.get("/profiles/{profile_id}/feed", response_model=FeedRead)
async def profile_feed(
    profile_id: uuid.UUID,
    _admin: SudoAdminUser,
    subscriptions: SubscriptionServiceDep,
    format: SubscriptionFormat = SubscriptionFormat.TEXT,
    version: RenderVersion = RenderVersion.V1,
    use_cache: bool = True,
) -> FeedRead:
    return await subscriptions.feed(
        _request(FeedScope.PROFILE, profile_id, format, version, use_cache)
    )


@router.get("/users/{user_id}/feed", response_model=FeedRead)
async def user_feed(
    user_id: uuid.UUID,
    admin: AdminUser,
    subscriptions: SubscriptionServiceDep,
    users: UserServiceDep,
    format: SubscriptionFormat = SubscriptionFormat.TEXT,
    version: RenderVersion = RenderVersion.V1,
    use_cache: bool = True,
) -> FeedRead:
    users.assert_can_manage(admin, await users.get(user_id))
    return await subscriptions.feed(_request(FeedScope.USER, user_id, format, version, use_cache))


@router.get(
    "/sub/{token}",
    summary="Public subscription feed",
    description=(
        "Returns the raw subscription config for VPN clients. "
        "Authenticates via a signed URL token instead of JWT."
    ),
    response_class=Response,
)
async def public_subscription(
    token: str,
    request: Request,
    settings: SettingsDep,
    subscriptions: SubscriptionServiceDep,
    app_settings: SettingsServiceDep,
    users: UserServiceDep,
    format: str | None = Query(default=None, alias="format"),
    user_agent: str = Header(default=""),
    x_hwid: str = Header(default=""),
) -> Response:
    user_id, scope, token_revision = verify_subscription_token(token, settings)
    # Only per-USER links are publicly servable. PROFILE/ASSIGNMENT scopes have
    # no per-user revocation or gating here and a PROFILE token would leak every
    # user's config on that profile — refuse them on the public endpoint.
    if scope is not FeedScope.USER:
        raise HTTPException(status_code=404)
    cfg = await app_settings.get_subscription()
    owner = await users.get(user_id)
    if owner.sub_revision != token_revision:
        raise AuthenticationError("Subscription link revoked.", code="sub_token_revoked")

    await users.touch_subscription(user_id, user_agent)

    is_browser_preview = format is None and _is_browser(user_agent)
    device_ok = True
    if owner.device_limit:
        client_ip = request.client.host if request.client else ""
        device_ok = await users.register_device(
            user_id, user_agent, client_ip, owner.device_limit, hwid=x_hwid
        )
        # A non-browser client over the limit is rejected outright. A browser
        # preview isn't hard-rejected (so the user can still see their status
        # page), but it must NOT be handed working configs — otherwise a forged
        # "Mozilla" UA is an unlimited-device bypass. device_ok gates the embed.
        if not device_ok and not is_browser_preview:
            raise HTTPException(status_code=403, detail="Device limit reached.")

    # Gate once, up front (lightweight quota read — no heavy TrafficRecord join),
    # so an expired/limited user still gets the status PAGE in a browser instead
    # of a raw 422 from the quota-enforcing feed() call below.
    quota = await subscriptions.get_user_quota(user_id)
    now_ts = int(time.time())
    not_servable = (
        not owner.is_active
        or (quota.expire_timestamp is not None and quota.expire_timestamp < now_ts)
        or (
            quota.traffic_limit_bytes is not None
            and quota.used_bytes >= quota.traffic_limit_bytes
        )
    )

    if is_browser_preview:
        configs: list[str] = []
        # device_ok MUST gate the embed: a browser preview isn't hard-rejected, but
        # an over-device-limit client (incl. a forged "Mozilla" UA) must not receive
        # working configs on the status page — that would be an unlimited-device
        # bypass.
        if not not_servable and device_ok:
            text_feed = await subscriptions.feed(
                _request(scope, user_id, SubscriptionFormat.TEXT, RenderVersion.V1, use_cache=True)
            )
            configs = [ln.strip() for ln in text_feed.content.splitlines() if "://" in ln]
            try:
                wg_feed = await subscriptions.feed(
                    _request(
                        scope,
                        user_id,
                        SubscriptionFormat.WIREGUARD_CONF,
                        RenderVersion.V1,
                        use_cache=True,
                    )
                )
                raw = wg_feed.content.strip()
                if "[Interface]" in raw:
                    blocks = ["[Interface]" + b for b in raw.split("[Interface]") if b.strip()]
                    configs.extend(b.strip() for b in blocks)
            except Exception:
                pass
        stats = await subscriptions.get_user_traffic_stats(user_id)
        status_label, status_tone = _status_text(owner, stats, cfg)
        custom = (getattr(cfg, "custom_page_html", "") or "").strip()
        if custom:
            page = render_custom_page(
                custom,
                title=cfg.profile_title or "XLink",
                username=owner.username,
                status=status_label,
                used=stats.used_bytes,
                total=stats.traffic_limit_bytes or None,
                expire_ts=stats.expire_timestamp or None,
                sub_url=str(request.url).split("?", 1)[0],
                configs=configs,
                support=cfg.support_link,
            )
        else:
            page = render_subscription_page(
                title=cfg.profile_title or "XLink",
                username=owner.username,
                status=status_label,
                status_tone=status_tone,
                used=stats.used_bytes,
                total=stats.traffic_limit_bytes or None,
                expire_ts=stats.expire_timestamp or None,
                sub_url=str(request.url).split("?", 1)[0],
                configs=configs,
                support=cfg.support_link,
                upload=stats.upload_bytes,
                download=stats.download_bytes,
            )

        return HTMLResponse(
            page,
            headers={
                "cache-control": "no-store",
                "content-security-policy": (
                    "default-src 'none'; style-src 'unsafe-inline'; "
                    "script-src 'unsafe-inline'; img-src 'self' data:; "
                    "connect-src 'self'; base-uri 'none'"
                ),
            },
        )

    try:
        detected_format = _detect_format(user_agent, format, cfg.rules)
    except _BlockedSubscriptionError:
        raise HTTPException(status_code=404) from None

    stats = await subscriptions.get_user_traffic_stats(user_id)

    if not_servable and cfg.placeholder_if_disabled:
        feed = await subscriptions.placeholder_feed(
            cfg.placeholder_remark, detected_format, RenderVersion.V1
        )
    else:
        feed = await subscriptions.feed(
            FeedRequest(
                scope=scope,
                subject_id=user_id,
                format=detected_format,
                version=RenderVersion.V1,
                use_cache=not cfg.shuffle_configs,
                shuffle=cfg.shuffle_configs,
                # Real client fetch: this is the "first use" that starts an
                # on-hold user's window.
                activate_first_use=True,
            )
        )

    userinfo = (
        f"upload={stats.upload_bytes}; download={stats.download_bytes}; "
        f"total={stats.traffic_limit_bytes}; expire={stats.expire_timestamp}"
    )

    content_type = _FORMAT_CONTENT_TYPES.get(detected_format, "text/plain")

    fname = (owner.username if owner else None) or cfg.profile_title or "xlink"
    fname = "".join(c for c in fname if c.isalnum() or c in "-_.") or "xlink"
    headers = {
        "subscription-userinfo": userinfo,
        "content-disposition": f'attachment; filename="{fname}"',
        "cache-control": "no-store",
        "profile-update-interval": str(max(1, cfg.update_interval_hours)),
        "profile-web-page-url": str(request.url).split("?", 1)[0],
    }
    if cfg.profile_title:
        encoded = base64.b64encode(cfg.profile_title.encode()).decode()
        headers["profile-title"] = f"base64:{encoded}"
    if cfg.support_link:
        headers["support-url"] = cfg.support_link

    return Response(content=feed.content, media_type=content_type, headers=headers)


async def _sub_base(request: Request, user: User, users: UserService) -> str:
    owner_id = getattr(user, "owner_id", None)
    if owner_id is not None:
        owner = await users.get(owner_id)
        if owner is not None and owner.subscription_url_prefix:
            return owner.subscription_url_prefix.rstrip("/")
    fwd_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if fwd_host and "api:" not in fwd_host and "localhost" not in fwd_host:
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        return f"{proto}://{fwd_host}".rstrip("/")
    return str(request.base_url).rstrip("/")


async def _issue_subscription_url(
    request: Request,
    subject: User,
    scope: FeedScope,
    settings: Settings,
    users: UserService,
) -> dict[str, str]:
    token = create_subscription_token(
        subject.id, scope, settings, revision=subject.sub_revision
    )
    base_url = await _sub_base(request, subject, users)
    prefix = settings.api_v1_prefix
    subscription_url = f"{base_url}{prefix}/subscriptions/sub/{token}"
    return {
        "token": token,
        "subscription_url": subscription_url,
    }


@router.get(
    "/my/token",
    summary="Get a subscription URL for the current user",
    tags=["subscriptions"],
)
async def get_my_subscription_token(
    request: Request,
    user: CurrentUser,
    settings: SettingsDep,
    users: UserServiceDep,
    scope: FeedScope = FeedScope.USER,
) -> dict[str, str]:
    return await _issue_subscription_url(request, user, scope, settings, users)


@router.get(
    "/users/{user_id}/token",
    summary="Get subscription URL for a specific user (admin)",
    tags=["subscriptions"],
)
async def get_user_subscription_token(
    user_id: uuid.UUID,
    request: Request,
    admin: AdminUser,
    settings: SettingsDep,
    users: UserServiceDep,
) -> dict[str, str]:
    target = await users.get(user_id)
    users.assert_can_manage(admin, target)
    return await _issue_subscription_url(request, target, FeedScope.USER, settings, users)
