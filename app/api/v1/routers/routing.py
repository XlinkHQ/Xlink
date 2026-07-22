from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.exceptions import NotFoundError
from app.dependencies.auth import AdminUser, SudoAdminUser
from app.dependencies.core import SessionDep
from app.domain.routing_rule import RoutingRule
from app.schemas.base import APIModel, InputModel

router = APIRouter(prefix="/routing", tags=["routing"])

_OUTBOUNDS = {"direct", "block", "warp", "proxy"}
_MATCH_TYPES = {"domain", "ip", "port"}


class RoutingRuleRead(APIModel):
    id: uuid.UUID
    name: str
    match_type: str
    match_values: str
    outbound: str
    enabled: bool
    priority: int


class RoutingRuleCreate(InputModel):
    name: str = Field(default="", max_length=128)
    match_type: str = Field(default="domain")
    match_values: str = Field(min_length=1, max_length=8192)
    outbound: str = Field(default="block", max_length=64)
    enabled: bool = Field(default=True)
    priority: int = Field(default=0, ge=0, le=9999)


class RoutingRuleUpdate(InputModel):
    name: str | None = Field(default=None, max_length=128)
    match_type: str | None = None
    match_values: str | None = Field(default=None, max_length=8192)
    outbound: str | None = Field(default=None, max_length=64)
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=9999)


class _Validated(BaseModel):
    match_type: str
    outbound: str


def _validate_match_values(match_type: str, match_values: str) -> None:
    import ipaddress

    from app.core.exceptions import ValidationError

    values = [v.strip() for v in match_values.split(",") if v.strip()]
    if not values:
        raise ValidationError("Rule needs at least one match value.", code="invalid_match_values")
    if match_type == "port":
        for v in values:
            parts = v.split("-")
            if not all(p.isdigit() and 1 <= int(p) <= 65535 for p in parts) or len(parts) > 2:
                raise ValidationError(
                    f"Invalid port value '{v}' — use a number or range like 8000-9000.",
                    code="invalid_match_values",
                )
    elif match_type == "ip":
        for v in values:
            if v.startswith(("geoip:", "ext:")):
                continue
            try:
                ipaddress.ip_network(v, strict=False)
            except ValueError as exc:
                raise ValidationError(
                    f"Invalid IP/CIDR value '{v}' — use an IP, CIDR, or geoip:xx.",
                    code="invalid_match_values",
                ) from exc


async def _validate(match_type: str, outbound: str, session, match_values: str | None = None) -> None:
    from app.core.exceptions import ValidationError
    from app.domain.outbound import Outbound

    if match_type not in _MATCH_TYPES:
        raise ValidationError("Invalid match type.", code="invalid_match_type")
    if match_values is not None:
        _validate_match_values(match_type, match_values)
    if outbound in _OUTBOUNDS:
        return
    row = await session.scalar(
        select(Outbound.enabled).where(Outbound.tag == outbound)
    )
    if row is None:
        raise ValidationError(
            "Unknown outbound — use a builtin or a defined outbound tag.", code="invalid_outbound"
        )
    if row is False:
        raise ValidationError(
            "That outbound is disabled — enable it before routing to it.",
            code="outbound_disabled",
        )


@router.get("/rules", response_model=list[RoutingRuleRead])
async def list_rules(_admin: AdminUser, session: SessionDep) -> list[RoutingRuleRead]:
    rows = (
        await session.execute(select(RoutingRule).order_by(RoutingRule.priority, RoutingRule.name))
    ).scalars().all()
    return [RoutingRuleRead.model_validate(r) for r in rows]


@router.post("/rules", response_model=RoutingRuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: RoutingRuleCreate,
    _admin: SudoAdminUser,
    session: SessionDep,
) -> RoutingRuleRead:
    await _validate(payload.match_type, payload.outbound, session, payload.match_values)
    rule = RoutingRule(
        name=payload.name,
        match_type=payload.match_type,
        match_values=payload.match_values,
        outbound=payload.outbound,
        enabled=payload.enabled,
        priority=payload.priority,
    )
    session.add(rule)
    await session.flush()
    return RoutingRuleRead.model_validate(rule)


@router.patch("/rules/{rule_id}", response_model=RoutingRuleRead)
async def update_rule(
    rule_id: uuid.UUID,
    payload: RoutingRuleUpdate,
    _admin: SudoAdminUser,
    session: SessionDep,
) -> RoutingRuleRead:
    rule = await session.get(RoutingRule, rule_id)
    if rule is None:
        raise NotFoundError("Rule not found.", code="rule_not_found")
    if payload.match_type is not None or payload.outbound is not None or payload.match_values is not None:
        await _validate(
            payload.match_type or rule.match_type,
            payload.outbound or rule.outbound,
            session,
            payload.match_values if payload.match_values is not None else rule.match_values,
        )
    for field in ("name", "match_type", "match_values", "outbound", "enabled", "priority"):
        value = getattr(payload, field)
        if value is not None:
            setattr(rule, field, value)
    await session.flush()
    return RoutingRuleRead.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: uuid.UUID,
    _admin: SudoAdminUser,
    session: SessionDep,
) -> None:
    rule = await session.get(RoutingRule, rule_id)
    if rule is None:
        raise NotFoundError("Rule not found.", code="rule_not_found")
    await session.delete(rule)
    await session.flush()


_OUTBOUND_TYPES = {
    "direct", "freedom", "block", "blackhole", "dns", "warp", "proxy",
    "socks", "http", "vmess", "vless", "trojan", "shadowsocks", "wireguard", "custom",
}
_ADDR_TYPES = {"socks", "http", "vmess", "vless", "trojan", "shadowsocks"}


class OutboundRead(APIModel):
    id: uuid.UUID
    tag: str
    type: str
    settings: dict
    enabled: bool


class OutboundCreate(InputModel):
    tag: str = Field(min_length=1, max_length=64)
    type: str = Field(default="direct")
    settings: dict = Field(default_factory=dict)
    enabled: bool = Field(default=True)


class OutboundUpdate(InputModel):
    tag: str | None = Field(default=None, max_length=64)
    type: str | None = None
    settings: dict | None = None
    enabled: bool | None = None


_RESERVED_TAGS = {"direct", "block", "warp", "proxy", "socks-out"}


def _validate_outbound(type_: str, settings: dict, tag: str | None = None) -> None:
    from app.agent.config_sync import _parse_host_port
    from app.core.exceptions import ValidationError

    if type_ not in _OUTBOUND_TYPES:
        raise ValidationError("Invalid outbound type.", code="invalid_outbound_type")
    if tag is not None and tag.strip().lower() in _RESERVED_TAGS:
        raise ValidationError(
            f"'{tag}' is a reserved tag — choose a different one.", code="reserved_outbound_tag"
        )
    if type_ in _ADDR_TYPES:
        addr = str(settings.get("address", "")).strip()
        host, port = _parse_host_port(addr)
        if host is None or port is None:
            raise ValidationError(
                "This outbound needs a valid host:port (bracket IPv6, e.g. [2001:db8::1]:1080).",
                code="invalid_outbound_address",
            )
    if type_ in ("vmess", "vless") and not (settings.get("id") or settings.get("uuid")):
        raise ValidationError("vmess/vless outbound needs a UUID (id).", code="invalid_outbound_id")
    if type_ in ("vmess", "vless") and str(settings.get("security", "")).lower() == "reality":
        if not settings.get("publicKey"):
            raise ValidationError(
                "A REALITY outbound needs a publicKey.", code="invalid_outbound_reality",
            )
    if type_ == "trojan" and not settings.get("password"):
        raise ValidationError("trojan outbound needs a password.", code="invalid_outbound_password")
    if type_ == "shadowsocks" and not settings.get("password"):
        raise ValidationError("shadowsocks outbound needs a password.", code="invalid_outbound_password")
    if type_ == "wireguard":
        if not settings.get("secretKey"):
            raise ValidationError("wireguard outbound needs a secretKey.", code="invalid_outbound_secretkey")
        if not settings.get("publicKey") or not settings.get("endpoint"):
            raise ValidationError(
                "wireguard outbound needs a peer publicKey and endpoint.",
                code="invalid_outbound_peer",
            )
    if type_ == "custom":
        raw = settings.get("raw")
        if not isinstance(raw, dict) or not raw.get("protocol"):
            raise ValidationError(
                "custom outbound needs a raw Xray outbound object with a non-empty protocol.",
                code="invalid_outbound_raw",
            )


class OutboundImportRequest(InputModel):
    text: str = Field(min_length=1)


class OutboundImportResult(APIModel):
    type: str
    settings: dict


@router.post("/outbounds/import", response_model=OutboundImportResult)
async def import_outbound(
    payload: OutboundImportRequest, _admin: SudoAdminUser
) -> OutboundImportResult:
    from app.api.v1.outbound_import import parse_import
    from app.core.exceptions import ValidationError

    parsed = parse_import(payload.text)
    if parsed is None:
        raise ValidationError(
            "Could not detect an outbound — paste a vless/vmess/trojan/ss link or an Xray config JSON.",
            code="outbound_import_failed",
        )
    return OutboundImportResult(type=parsed["type"], settings=parsed["settings"])


class OutboundPingRequest(InputModel):
    address: str = Field(min_length=1)


class OutboundPingResult(APIModel):
    ok: bool
    latency_ms: int | None
    detail: str


@router.post("/outbounds/ping", response_model=OutboundPingResult)
async def ping_outbound_address(payload: OutboundPingRequest, _admin: SudoAdminUser) -> OutboundPingResult:
    from app.agent.config_sync import _parse_host_port
    from app.services.outbound_ping import _tcp_ping

    host, port = _parse_host_port(payload.address.strip())
    if host is None or port is None:
        return OutboundPingResult(ok=False, latency_ms=None, detail="Invalid host:port.")
    r = await _tcp_ping(payload.address.strip())
    return OutboundPingResult(**r)


@router.post("/outbounds/{outbound_id}/ping", response_model=OutboundPingResult)
async def ping_outbound(
    outbound_id: uuid.UUID, _admin: SudoAdminUser, session: SessionDep
) -> OutboundPingResult:
    from app.domain.outbound import Outbound
    from app.services.outbound_ping import ping_outbound as run_ping

    row = await session.get(Outbound, outbound_id)
    if row is None:
        raise NotFoundError("Outbound not found.", code="outbound_not_found")
    settings = row.settings or {}
    address = str(settings.get("address") or settings.get("endpoint") or "")
    r = await run_ping(row.type, settings, address)
    return OutboundPingResult(**r)


@router.get("/outbounds", response_model=list[OutboundRead])
async def list_outbounds(_admin: SudoAdminUser, session: SessionDep) -> list[OutboundRead]:
    from app.domain.outbound import Outbound

    rows = (
        await session.execute(select(Outbound).order_by(Outbound.tag))
    ).scalars().all()
    return [OutboundRead.model_validate(r) for r in rows]


@router.post("/outbounds", response_model=OutboundRead, status_code=status.HTTP_201_CREATED)
async def create_outbound(
    payload: OutboundCreate, _admin: SudoAdminUser, session: SessionDep
) -> OutboundRead:
    from app.domain.outbound import Outbound

    _validate_outbound(payload.type, payload.settings, payload.tag)
    row = Outbound(
        tag=payload.tag, type=payload.type, settings=payload.settings, enabled=payload.enabled
    )
    session.add(row)
    await session.flush()
    return OutboundRead.model_validate(row)


@router.patch("/outbounds/{outbound_id}", response_model=OutboundRead)
async def update_outbound(
    outbound_id: uuid.UUID,
    payload: OutboundUpdate,
    _admin: SudoAdminUser,
    session: SessionDep,
) -> OutboundRead:
    from app.domain.outbound import Outbound

    row = await session.get(Outbound, outbound_id)
    if row is None:
        raise NotFoundError("Outbound not found.", code="outbound_not_found")
    new_type = payload.type or row.type
    new_settings = payload.settings if payload.settings is not None else row.settings
    _validate_outbound(new_type, new_settings, payload.tag)
    if payload.enabled is False and row.enabled:
        from app.core.exceptions import ValidationError

        ref = await session.scalar(
            select(RoutingRule.id)
            .where(RoutingRule.outbound == row.tag, RoutingRule.enabled.is_(True))
            .limit(1)
        )
        if ref is not None:
            raise ValidationError(
                "This outbound is used by an enabled routing rule — disable those rules first.",
                code="outbound_in_use",
            )
    old_tag = row.tag
    for field in ("tag", "type", "settings", "enabled"):
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, value)
    if payload.tag is not None and payload.tag != old_tag:
        from sqlalchemy import update as sql_update

        await session.execute(
            sql_update(RoutingRule)
            .where(RoutingRule.outbound == old_tag)
            .values(outbound=payload.tag)
        )
    await session.flush()
    return OutboundRead.model_validate(row)


@router.delete("/outbounds/{outbound_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_outbound(
    outbound_id: uuid.UUID, _admin: SudoAdminUser, session: SessionDep
) -> None:
    from app.domain.outbound import Outbound

    row = await session.get(Outbound, outbound_id)
    if row is None:
        raise NotFoundError("Outbound not found.", code="outbound_not_found")
    from app.core.exceptions import ValidationError

    ref = await session.scalar(
        select(RoutingRule.id).where(RoutingRule.outbound == row.tag).limit(1)
    )
    if ref is not None:
        raise ValidationError(
            "This outbound is used by a routing rule — remove those rules first.",
            code="outbound_in_use",
        )
    await session.delete(row)
    await session.flush()
