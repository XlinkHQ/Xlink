from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import orjson
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.domain import DriftSeverity, NodeDriftReport
from app.agent.repository import NodeDriftRepository
from app.core.logging import get_logger
from app.domain.client_assignment import AssignmentStatus, ClientAssignment
from app.domain.node import Node
from app.domain.profile import Profile
from app.domain.user import User

logger = get_logger("xlink.config_sync")

_DESIRED_VERSION_KEY = "desired_config_version"


def _parse_host_port(value: str) -> tuple[str | None, int | None]:
    value = value.strip()
    if value.startswith("["):
        end = value.find("]")
        if end == -1:
            return None, None
        host = value[1:end]
        rest = value[end + 1 :]
        port_str = rest[1:] if rest.startswith(":") else ""
    else:
        host, _, port_str = value.rpartition(":")
        if ":" in host:
            return (value, None) if value else (None, None)
    if not host:
        return None, None
    if not port_str:
        return host, None
    if not port_str.isdigit():
        return None, None
    port = int(port_str)
    if not (1 <= port <= 65535):
        return None, None
    return host, port


def _stream_settings(s: dict[str, Any]) -> dict[str, Any] | None:
    net = s.get("network")
    sec = s.get("security")
    if not net and not sec:
        return None
    stream: dict[str, Any] = {"network": net or "tcp"}
    if net == "ws":
        ws: dict[str, Any] = {}
        if s.get("path"):
            ws["path"] = s["path"]
        if s.get("host"):
            ws["host"] = s["host"]
        stream["wsSettings"] = ws
    elif net == "grpc":
        stream["grpcSettings"] = {"serviceName": s.get("serviceName", "")}
    elif net in ("httpupgrade", "xhttp"):
        key = "httpupgradeSettings" if net == "httpupgrade" else "xhttpSettings"
        block: dict[str, Any] = {}
        if s.get("path"):
            block["path"] = s["path"]
        if s.get("host"):
            block["host"] = s["host"]
        stream[key] = block
    if sec == "tls":
        stream["security"] = "tls"
        tls: dict[str, Any] = {}
        if s.get("sni"):
            tls["serverName"] = s["sni"]
        if s.get("alpn"):
            tls["alpn"] = [a.strip() for a in str(s["alpn"]).split(",") if a.strip()]
        if s.get("fingerprint"):
            tls["fingerprint"] = s["fingerprint"]
        if s.get("allowInsecure"):
            tls["allowInsecure"] = True
        stream["tlsSettings"] = tls
    elif sec == "reality":
        stream["security"] = "reality"
        r: dict[str, Any] = {}
        for k_in, k_out in (
            ("publicKey", "publicKey"),
            ("sni", "serverName"),
            ("fingerprint", "fingerprint"),
            ("shortId", "shortId"),
            ("spiderX", "spiderX"),
        ):
            if s.get(k_in):
                r[k_out] = s[k_in]
        r.setdefault("fingerprint", "chrome")
        stream["realitySettings"] = r
    return stream


def _build_outbound(tag: str, type_: str, settings: dict[str, Any]) -> dict[str, Any] | None:
    if type_ == "custom":
        raw = settings.get("raw")
        if isinstance(raw, dict) and raw.get("protocol"):
            return {**raw, "tag": tag}
        return None
    if type_ in ("direct", "freedom", "proxy"):
        f: dict[str, Any] = {}
        if settings.get("domainStrategy"):
            f["domainStrategy"] = settings["domainStrategy"]
        return {"tag": tag, "protocol": "freedom", "settings": f}
    if type_ in ("block", "blackhole"):
        return {"tag": tag, "protocol": "blackhole", "settings": {}}
    if type_ == "dns":
        return {"tag": tag, "protocol": "dns", "settings": {}}
    if type_ in ("socks", "http"):
        host, port = _parse_host_port(str(settings.get("address", "")))
        if host is None or port is None:
            return None
        server: dict[str, Any] = {"address": host, "port": port}
        user = settings.get("username")
        if user:
            server["users"] = [{"user": user, "pass": settings.get("password", "")}]
        out: dict[str, Any] = {"tag": tag, "protocol": type_, "settings": {"servers": [server]}}
        stream = _stream_settings({**settings, "security": None})
        if stream:
            out["streamSettings"] = stream
        return out
    if type_ in ("vmess", "vless"):
        host, port = _parse_host_port(str(settings.get("address", "")))
        if host is None or port is None:
            return None
        uid = settings.get("id") or settings.get("uuid")
        if not uid:
            return None
        user_obj: dict[str, Any] = {"id": uid}
        if type_ == "vless":
            user_obj["encryption"] = "none"
            if settings.get("flow"):
                user_obj["flow"] = settings["flow"]
        else:
            user_obj["security"] = settings.get("encryption", "auto")
        out = {
            "tag": tag,
            "protocol": type_,
            "settings": {"vnext": [{"address": host, "port": port, "users": [user_obj]}]},
        }
        stream = _stream_settings(settings)
        if stream:
            out["streamSettings"] = stream
        return out
    if type_ == "trojan":
        host, port = _parse_host_port(str(settings.get("address", "")))
        if host is None or port is None or not settings.get("password"):
            return None
        srv: dict[str, Any] = {"address": host, "port": port, "password": settings["password"]}
        if settings.get("flow"):
            srv["flow"] = settings["flow"]
        out = {"tag": tag, "protocol": "trojan", "settings": {"servers": [srv]}}
        stream = _stream_settings(settings)
        if stream:
            out["streamSettings"] = stream
        return out
    if type_ == "shadowsocks":
        host, port = _parse_host_port(str(settings.get("address", "")))
        if host is None or port is None or not settings.get("password"):
            return None
        return {
            "tag": tag,
            "protocol": "shadowsocks",
            "settings": {
                "servers": [
                    {
                        "address": host,
                        "port": port,
                        "method": settings.get("method", "aes-256-gcm"),
                        "password": settings["password"],
                    }
                ]
            },
        }
    if type_ == "wireguard":
        if not settings.get("secretKey"):
            return None
        peer: dict[str, Any] = {
            "publicKey": settings.get("publicKey", ""),
            "endpoint": settings.get("endpoint", ""),
            "allowedIPs": [
                a.strip()
                for a in str(settings.get("allowedIPs", "0.0.0.0/0, ::/0")).split(",")
                if a.strip()
            ],
        }
        if settings.get("preSharedKey"):
            peer["preSharedKey"] = settings["preSharedKey"]
        wg: dict[str, Any] = {
            "secretKey": settings["secretKey"],
            "address": [
                a.strip()
                for a in str(settings.get("address", "172.16.0.2/32")).split(",")
                if a.strip()
            ],
            "peers": [peer],
        }
        if str(settings.get("mtu", "")).strip().isdigit():
            wg["mtu"] = int(settings["mtu"])
        if settings.get("reserved"):
            wg["reserved"] = [
                int(x) for x in str(settings["reserved"]).split(",") if x.strip().isdigit()
            ]
        return {"tag": tag, "protocol": "wireguard", "settings": wg}
    return None


def _singbox_route_rule(
    match_type: str, values: list[str], outbound: str
) -> tuple[dict[str, Any] | None, list[str]]:
    rule: dict[str, Any] = {"outbound": outbound}
    dropped: list[str] = []
    if match_type == "ip":
        cidrs = [v for v in values if not v.startswith(("geoip:", "ext:"))]
        dropped = [v for v in values if v.startswith(("geoip:", "ext:"))]
        if not cidrs:
            return None, dropped
        rule["ip_cidr"] = cidrs
    elif match_type == "port":
        ports: list[int] = []
        ranges: list[str] = []
        for v in values:
            if "-" in v:
                lo, _, hi = v.partition("-")
                ranges.append(f"{lo}:{hi}")
            elif v.isdigit():
                ports.append(int(v))
            else:
                dropped.append(v)
        if ports:
            rule["port"] = ports
        if ranges:
            rule["port_range"] = ranges
        if not ports and not ranges:
            return None, dropped
    else:
        exact: list[str] = []
        suffix: list[str] = []
        for v in values:
            if v.startswith(("geosite:", "ext:")):
                dropped.append(v)
            elif v.startswith("full:"):
                exact.append(v[len("full:") :])
            elif v.startswith("domain:"):
                suffix.append(v[len("domain:") :])
            else:
                suffix.append(v)
        if exact:
            rule["domain"] = exact
        if suffix:
            rule["domain_suffix"] = suffix
        if not exact and not suffix:
            return None, dropped
    return rule, dropped


def _build_singbox_outbound(
    tag: str, type_: str, settings: dict[str, Any]
) -> dict[str, Any] | None:
    if type_ in ("direct", "freedom", "proxy"):
        return {"type": "direct", "tag": tag}
    if type_ in ("block", "blackhole"):
        return {"type": "block", "tag": tag}
    if type_ == "dns":
        return {"type": "dns", "tag": tag}
    if type_ == "custom":
        raw = settings.get("raw")
        if isinstance(raw, dict) and raw.get("type"):
            return {**raw, "tag": tag}
        return None
    if type_ in ("socks", "http"):
        host, port = _parse_host_port(str(settings.get("address", "")))
        if host is None or port is None:
            return None
        out: dict[str, Any] = {"type": type_, "tag": tag, "server": host, "server_port": port}
        if settings.get("username"):
            out["username"] = str(settings["username"])
            out["password"] = str(settings.get("password", ""))
        return out
    if type_ == "shadowsocks":
        host, port = _parse_host_port(str(settings.get("address", "")))
        if host is None or port is None or not settings.get("password"):
            return None
        return {
            "type": "shadowsocks",
            "tag": tag,
            "server": host,
            "server_port": port,
            "method": settings.get("method", "aes-256-gcm"),
            "password": settings["password"],
        }
    if type_ in ("vmess", "vless"):
        host, port = _parse_host_port(str(settings.get("address", "")))
        uid = settings.get("id") or settings.get("uuid")
        if host is None or port is None or not uid:
            return None
        out = {"type": type_, "tag": tag, "server": host, "server_port": port, "uuid": uid}
        if type_ == "vless" and settings.get("flow"):
            out["flow"] = settings["flow"]
        return out
    if type_ == "trojan":
        host, port = _parse_host_port(str(settings.get("address", "")))
        if host is None or port is None or not settings.get("password"):
            return None
        return {
            "type": "trojan",
            "tag": tag,
            "server": host,
            "server_port": port,
            "password": settings["password"],
        }
    if type_ == "wireguard":
        if not settings.get("secretKey"):
            return None
        endpoint = settings.get("endpoint", "")
        wg_host, _wg_port = _parse_host_port(endpoint)
        return {
            "type": "wireguard",
            "tag": tag,
            "server": wg_host or endpoint,
            "server_port": _wg_endpoint_port(endpoint),
            "local_address": [
                a.strip()
                for a in str(settings.get("address", "172.16.0.2/32")).split(",")
                if a.strip()
            ],
            "private_key": settings["secretKey"],
            "peer_public_key": settings.get("publicKey", ""),
            **(
                {"pre_shared_key": settings["preSharedKey"]} if settings.get("preSharedKey") else {}
            ),
            **(
                {
                    "reserved": [
                        int(x) for x in str(settings["reserved"]).split(",") if x.strip().isdigit()
                    ]
                }
                if settings.get("reserved")
                else {}
            ),
        }
    return None


_DEFAULT_WARP_ENDPOINT_PORT = 2408


def _wg_endpoint_port(endpoint: str) -> int:
    _, port = _parse_host_port(endpoint)
    return port if port is not None else _DEFAULT_WARP_ENDPOINT_PORT


def _user_serviceable(now: datetime):
    return and_(
        User.is_active.is_(True),
        User.removed.is_(False),
        User.on_hold.is_(False),
        or_(User.expire_at.is_(None), User.expire_at > now),
        or_(
            User.data_limit_bytes.is_(None),
            User.users_data_usage < User.data_limit_bytes,
        ),
    )


_AGENT_CRED_ALLOW = frozenset(
    {
        "uuid",
        "password",
        "private_key",
        "public_key",
        "preshared_key",
        "server_public_key",
        "address",
        "short_id",
        "shortid",
        "obfs_password",
        "method",
        "flow",
        "username",
    }
)


def _agent_credentials(credentials: Any) -> dict[str, Any]:
    if not credentials:
        return {}
    return {k: v for k, v in dict(credentials).items() if k.lower() in _AGENT_CRED_ALLOW}


def _agent_settings(settings: Any) -> dict[str, Any]:
    return dict(settings or {})


_REPORTED_VERSION_KEY = "reported_config_version"
_REPORTED_STATE_KEY = "reported_state"


def config_version(config: dict[str, Any]) -> str:
    stable = dict(config)
    clients = stable.get("clients")
    if isinstance(clients, list):
        stable["clients"] = [
            {k: v for k, v in c.items() if k != "used_bytes"} if isinstance(c, dict) else c
            for c in clients
        ]
    raw = orjson.dumps(stable, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(raw).hexdigest()[:32]


class ConfigSyncService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._drift = NodeDriftRepository(session)

    async def desired_configs_for_nodes(
        self, node_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dict[str, Any]]:
        if not node_ids:
            return {}
        result: dict[uuid.UUID, list[dict[str, Any]]] = {nid: [] for nid in node_ids}
        now = datetime.now(UTC)
        stmt = (
            select(ClientAssignment, Profile, User)
            .join(Profile, ClientAssignment.profile_id == Profile.id)
            .join(User, ClientAssignment.user_id == User.id)
            .where(
                ClientAssignment.node_id.in_(node_ids),
                ClientAssignment.status == AssignmentStatus.ACTIVE,
                _user_serviceable(now),
            )
            .order_by(ClientAssignment.node_id, ClientAssignment.id.asc())
        )
        rows = (await self._session.execute(stmt)).all()
        for assignment, profile, user in rows:
            result.setdefault(assignment.node_id, []).append(
                {
                    "assignment_id": str(assignment.id),
                    "user_id": str(assignment.user_id),
                    "provider_client_id": assignment.provider_client_id,
                    "provider_kind": assignment.provider_kind.value,
                    "protocol": profile.protocol,
                    "profile_slug": profile.slug,
                    "settings": _agent_settings(profile.settings),
                    "credentials": _agent_credentials(assignment.credentials),
                    "data_limit_bytes": user.data_limit_bytes,
                    "used_bytes": int(user.users_data_usage or 0),
                }
            )
        certs = await self._cert_map()
        for clients in result.values():
            self._attach_certs(clients, certs)
        return {
            nid: {
                "clients": clients,
                "client_count": len(clients),
                "core_templates": await self._core_templates(nid),
            }
            for nid, clients in result.items()
        }

    async def desired_config(self, node_id: uuid.UUID) -> dict[str, Any]:
        now = datetime.now(UTC)
        stmt = (
            select(ClientAssignment, Profile, User)
            .join(Profile, ClientAssignment.profile_id == Profile.id)
            .join(User, ClientAssignment.user_id == User.id)
            .where(
                ClientAssignment.node_id == node_id,
                ClientAssignment.status == AssignmentStatus.ACTIVE,
                _user_serviceable(now),
            )
            .order_by(ClientAssignment.id.asc())
        )
        rows = (await self._session.execute(stmt)).all()
        clients = [
            {
                "assignment_id": str(assignment.id),
                "user_id": str(assignment.user_id),
                "provider_client_id": assignment.provider_client_id,
                "provider_kind": assignment.provider_kind.value,
                "protocol": profile.protocol,
                "profile_slug": profile.slug,
                "settings": _agent_settings(profile.settings),
                "credentials": _agent_credentials(assignment.credentials),
                "data_limit_bytes": user.data_limit_bytes,
                "used_bytes": int(user.users_data_usage or 0),
            }
            for assignment, profile, user in rows
        ]
        self._attach_certs(clients, await self._cert_map())
        return {
            "clients": clients,
            "client_count": len(clients),
            "core_templates": await self._core_templates(node_id),
        }

    async def _cert_map(self) -> dict[str, tuple[str, str]]:
        from app.domain.certificate import Certificate, CertificateStatus

        stmt = select(Certificate).where(Certificate.status == CertificateStatus.ACTIVE)
        rows = (await self._session.execute(stmt)).scalars().all()
        return {c.domain.lower(): (c.cert_pem, c.key_pem) for c in rows if c.cert_pem and c.key_pem}

    def _attach_certs(
        self, clients: list[dict[str, Any]], certs: dict[str, tuple[str, str]]
    ) -> None:
        if not certs:
            return
        for cl in clients:
            settings = cl.get("settings") or {}
            if str(settings.get("security", "")).lower() != "tls":
                continue
            sni = str(settings.get("sni") or settings.get("host") or "").strip().lower()
            material = certs.get(sni)
            if material is None:
                continue
            settings["cert_pem"] = material[0]
            settings["key_pem"] = material[1]
            cl["settings"] = settings

    async def _core_templates(self, node_id: uuid.UUID | None = None) -> dict[str, Any]:
        from app.domain.app_settings import SINGLETON_ID, AppSettings

        row = await self._session.get(AppSettings, SINGLETON_ID)
        raw = row.xray_core_template if row else "{}"
        try:
            parsed = json.loads(raw or "{}")
            templates = parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            templates = {}

        node = await self._session.get(Node, node_id) if node_id is not None else None
        await self._merge_warp_and_routing(templates, row, node)
        return templates

    async def _merge_warp_and_routing(self, templates: dict[str, Any], row, node=None) -> None:
        from app.domain.routing_rule import RoutingRule

        xray = dict(templates.get("xray") or {}) if isinstance(templates.get("xray"), dict) else {}
        outbounds = list(xray.get("outbounds") or [])
        routing = dict(xray.get("routing") or {})
        rules = list(routing.get("rules") or [])
        changed = False

        if (
            row is not None
            and row.warp_enabled
            and row.warp_private_key
            and row.warp_public_key
            and row.warp_address
            and not any(o.get("tag") == "warp" for o in outbounds)
        ):
            outbounds.append(
                {
                    "tag": "warp",
                    "protocol": "wireguard",
                    "settings": {
                        "secretKey": row.warp_private_key,
                        "address": [a.strip() for a in row.warp_address.split(",") if a.strip()],
                        "peers": [
                            {
                                "publicKey": row.warp_public_key,
                                "endpoint": row.warp_endpoint,
                            }
                        ],
                        **(
                            {
                                "reserved": [
                                    int(x)
                                    for x in row.warp_reserved.split(",")
                                    if x.strip().isdigit()
                                ]
                            }
                            if row.warp_reserved
                            else {}
                        ),
                    },
                }
            )
            changed = True

        db_rules = (
            (
                await self._session.execute(
                    select(RoutingRule)
                    .where(RoutingRule.enabled.is_(True))
                    .order_by(RoutingRule.priority, RoutingRule.name, RoutingRule.id)
                )
            )
            .scalars()
            .all()
        )
        db_built: list[dict[str, Any]] = []
        for rr in db_rules:
            values = [v.strip() for v in rr.match_values.split(",") if v.strip()]
            if not values:
                continue
            rule: dict[str, Any] = {"type": "field", "outboundTag": rr.outbound}
            if rr.match_type == "ip":
                rule["ip"] = values
            elif rr.match_type == "port":
                rule["port"] = ",".join(values)
            else:
                rule["domain"] = values
            db_built.append(rule)
        if db_built:
            rules = db_built + rules
            changed = True

        from app.domain.outbound import Outbound

        db_outbounds = (
            (
                await self._session.execute(
                    select(Outbound).where(Outbound.enabled.is_(True)).order_by(Outbound.tag)
                )
            )
            .scalars()
            .all()
        )
        existing_tags = {o.get("tag") for o in outbounds}
        for ob in db_outbounds:
            if ob.tag in existing_tags:
                continue
            try:
                built = _build_outbound(ob.tag, ob.type, ob.settings or {})
            except Exception as exc:
                logger.warning("outbound_build_failed", tag=ob.tag, type=ob.type, error=str(exc))
                built = None
            if built is not None:
                outbounds.append(built)
                changed = True

        referenced = {
            r.get("outboundTag") for r in rules if isinstance(r, dict) and r.get("outboundTag")
        }
        present = {o.get("tag") for o in outbounds if isinstance(o, dict)}
        _BUILTIN_FALLBACK = {
            "direct": ("freedom", {}),
            "proxy": ("freedom", {}),
            "block": ("blackhole", {}),
            "dns": ("dns", {}),
        }
        for tag in referenced - present:
            spec = _BUILTIN_FALLBACK.get(tag)
            if spec is not None:
                built = _build_outbound(tag, spec[0], spec[1])
                if built is not None:
                    outbounds.append(built)
                    present.add(tag)
                    changed = True
        still_missing = referenced - present
        if still_missing:
            kept = [
                r
                for r in rules
                if not (isinstance(r, dict) and r.get("outboundTag") in still_missing)
            ]
            if len(kept) != len(rules):
                logger.warning("routing_rule_dropped_missing_outbound", tags=sorted(still_missing))
                rules = kept
                changed = True

        if changed or rules:
            if not any(o.get("tag") == "direct" for o in outbounds):
                direct = _build_outbound("direct", "freedom", {})
                if direct is not None:
                    outbounds.insert(0, direct)
                    changed = True
            else:
                outbounds = [o for o in outbounds if o.get("tag") == "direct"] + [
                    o for o in outbounds if o.get("tag") != "direct"
                ]
                changed = True

        if node is not None and node.socks_enabled and node.socks_address:
            host, port = _parse_host_port(node.socks_address)
            if not host or port is None:
                logger.warning(
                    "socks_address_invalid", node_id=str(node.id), address=node.socks_address
                )
            else:
                if not any(o.get("tag") == "socks-out" for o in outbounds):
                    server: dict[str, Any] = {"address": host, "port": port}
                    if node.socks_username:
                        server["users"] = [
                            {"user": node.socks_username, "pass": node.socks_password or ""}
                        ]
                    socks_outbound = {
                        "tag": "socks-out",
                        "protocol": "socks",
                        "settings": {"servers": [server]},
                    }
                    outbounds = [socks_outbound] + [
                        o for o in outbounds if o.get("tag") != "socks-out"
                    ]
                    changed = True

        if changed:
            routing["rules"] = rules
            xray["outbounds"] = outbounds
            xray["routing"] = routing
            templates["xray"] = xray

        if isinstance(templates.get("sing-box"), dict):
            self._merge_singbox_routing(templates, row, db_rules, db_outbounds, node)

        if db_rules:
            for core in ("hysteria", "wireguard"):
                if isinstance(templates.get(core), dict):
                    logger.warning(
                        "routing_rules_unsupported_by_core",
                        core=core,
                        rule_count=len(db_rules),
                    )

    def _merge_singbox_routing(
        self, templates: dict[str, Any], row, db_rules, db_outbounds, node
    ) -> None:
        sb = dict(templates.get("sing-box") or {})
        outbounds = list(sb.get("outbounds") or [])
        route = dict(sb.get("route") or {})
        rules = list(route.get("rules") or [])
        changed = False

        present = {o.get("tag") for o in outbounds if isinstance(o, dict)}

        if (
            row is not None
            and row.warp_enabled
            and row.warp_private_key
            and row.warp_address
            and "warp" not in present
        ):
            warp_ob = _build_singbox_outbound(
                "warp",
                "wireguard",
                {
                    "secretKey": row.warp_private_key,
                    "publicKey": row.warp_public_key,
                    "endpoint": row.warp_endpoint,
                    "address": row.warp_address,
                    "reserved": row.warp_reserved,
                },
            )
            if warp_ob is not None:
                outbounds.append(warp_ob)
                present.add("warp")
                changed = True

        for ob in db_outbounds:
            if ob.tag in present:
                continue
            try:
                built = _build_singbox_outbound(ob.tag, ob.type, ob.settings or {})
            except Exception as exc:
                logger.warning(
                    "singbox_outbound_build_failed", tag=ob.tag, type=ob.type, error=str(exc)
                )
                built = None
            if built is None:
                logger.warning("singbox_outbound_unsupported", tag=ob.tag, type=ob.type)
                continue
            outbounds.append(built)
            present.add(ob.tag)
            changed = True

        _BUILTIN = {
            "direct": ("direct", {}),
            "proxy": ("direct", {}),
            "block": ("block", {}),
            "dns": ("dns", {}),
        }
        db_built: list[dict[str, Any]] = []
        dropped_selectors: dict[str, list[str]] = {}
        for rr in db_rules:
            values = [v.strip() for v in rr.match_values.split(",") if v.strip()]
            if not values:
                continue
            rule, dropped = _singbox_route_rule(rr.match_type, values, rr.outbound)
            if dropped:
                dropped_selectors.setdefault(rr.match_type, []).extend(dropped)
            if rule is None:
                continue
            db_built.append(rule)
        if dropped_selectors:
            logger.warning(
                "singbox_route_selectors_unsupported",
                dropped={k: sorted(set(v)) for k, v in dropped_selectors.items()},
            )
        if db_built:
            rules = db_built + rules
            changed = True

        referenced = {r.get("outbound") for r in rules if isinstance(r, dict) and r.get("outbound")}
        for tag in referenced - present:
            spec = _BUILTIN.get(tag)
            if spec is not None:
                built = _build_singbox_outbound(tag, spec[0], spec[1])
                if built is not None:
                    outbounds.append(built)
                    present.add(tag)
                    changed = True
        still_missing = referenced - present
        if still_missing:
            kept = [
                r for r in rules if not (isinstance(r, dict) and r.get("outbound") in still_missing)
            ]
            if len(kept) != len(rules):
                logger.warning(
                    "singbox_routing_rule_dropped_missing_outbound", tags=sorted(still_missing)
                )
                rules = kept
                changed = True

        if changed or rules:
            if "direct" not in present:
                direct = _build_singbox_outbound("direct", "direct", {})
                if direct is not None:
                    outbounds.insert(0, direct)
                    present.add("direct")
                    changed = True
            if not route.get("final"):
                route["final"] = "direct"
                changed = True

        if node is not None and node.socks_enabled and node.socks_address:
            host, port = _parse_host_port(node.socks_address)
            if not host or port is None:
                logger.warning(
                    "socks_address_invalid", node_id=str(node.id), address=node.socks_address
                )
            elif "socks-out" not in present:
                socks_outbound: dict[str, Any] = {
                    "type": "socks",
                    "tag": "socks-out",
                    "server": host,
                    "server_port": port,
                }
                if node.socks_username:
                    socks_outbound["username"] = node.socks_username
                    socks_outbound["password"] = node.socks_password or ""
                outbounds.append(socks_outbound)
                present.add("socks-out")
                route["final"] = "socks-out"
                changed = True

        if changed:
            route["rules"] = rules
            sb["route"] = route
            sb["outbounds"] = outbounds
            templates["sing-box"] = sb

    async def build_snapshot(
        self,
        node: Node,
        *,
        cache: Any | None = None,
        known_version: str | None = None,
        cache_ttl: int = 300,
    ) -> dict[str, Any]:
        if cache is not None:
            cached = await self._read_cached_snapshot(cache, node)
            if cached is not None:
                if known_version is not None and known_version == cached["config_version"]:
                    return {
                        "node_id": node.id,
                        "config_version": cached["config_version"],
                        "config": {},
                        "assignment_count": cached["assignment_count"],
                        "unchanged": True,
                    }
                return {**cached, "unchanged": False}

        config = await self.desired_config(node.id)

        config["restart_nonce"] = node.node_metadata.get("restart_nonce", 0)
        version = config_version(config)
        metadata = dict(node.node_metadata)
        if metadata.get(_DESIRED_VERSION_KEY) != version:
            metadata[_DESIRED_VERSION_KEY] = version
            node.node_metadata = metadata
            await self._session.flush()
        snapshot = {
            "node_id": node.id,
            "config_version": version,
            "config": config,
            "assignment_count": config["client_count"],
        }
        if cache is not None:
            await self._write_cached_snapshot(cache, node, snapshot, cache_ttl)
        if known_version is not None and known_version == version:
            return {
                "node_id": node.id,
                "config_version": version,
                "config": {},
                "assignment_count": config["client_count"],
                "unchanged": True,
            }
        return {**snapshot, "unchanged": False}

    async def _read_cached_snapshot(self, cache: Any, node: Node) -> dict[str, Any] | None:
        try:
            raw = await cache.get_node_config(node.id)
        except Exception as exc:
            logger.warning("config_cache_read_failed", node_id=str(node.id), error=str(exc))
            return None
        if not isinstance(raw, dict) or "config_version" not in raw:
            return None
        return {
            "node_id": node.id,
            "config_version": raw["config_version"],
            "config": raw.get("config") or {},
            "assignment_count": int(raw.get("assignment_count", 0) or 0),
        }

    async def _write_cached_snapshot(
        self, cache: Any, node: Node, snapshot: dict[str, Any], ttl: int
    ) -> None:
        try:
            await cache.set_node_config(
                node.id,
                {
                    "config_version": snapshot["config_version"],
                    "config": snapshot["config"],
                    "assignment_count": snapshot["assignment_count"],
                },
                ttl,
            )
        except Exception:
            logger.warning("node_config_snapshot_cache_write_failed", node_id=str(node.id))

    async def record_reported_state(
        self,
        node: Node,
        *,
        config_version_value: str | None,
        agent_version: str | None,
        applied: dict[str, Any],
        provider_status: dict[str, str],
    ) -> None:
        metadata = dict(node.node_metadata)
        if config_version_value is not None:
            metadata[_REPORTED_VERSION_KEY] = config_version_value
        state = {
            "agent_version": agent_version,
            "provider_status": provider_status,
            "reported_at": datetime.now(UTC).isoformat(),
        }
        if applied:
            state["applied"] = applied
        elif isinstance(metadata.get(_REPORTED_STATE_KEY), dict):
            state["applied"] = metadata[_REPORTED_STATE_KEY].get("applied", {})
        metadata[_REPORTED_STATE_KEY] = state
        node.node_metadata = metadata
        await self._session.flush()

    async def detect_drift(self, node: Node) -> NodeDriftReport:
        config = await self.desired_config(node.id)

        config["restart_nonce"] = node.node_metadata.get("restart_nonce", 0)
        return await self.detect_drift_with_config(node, config)

    async def detect_drift_with_config(self, node: Node, config: dict[str, Any]) -> NodeDriftReport:
        desired_version = config_version(config)
        metadata = dict(node.node_metadata)
        if metadata.get(_DESIRED_VERSION_KEY) != desired_version:
            metadata[_DESIRED_VERSION_KEY] = desired_version
            node.node_metadata = metadata
            await self._session.flush()
        reported_version = metadata.get(_REPORTED_VERSION_KEY)
        reported_state = metadata.get(_REPORTED_STATE_KEY) or {}
        applied = reported_state.get("applied", {}) if isinstance(reported_state, dict) else {}
        locally_limited = int(applied.get("locally_limited", 0)) if isinstance(applied, dict) else 0

        severity = self._severity(desired_version, reported_version)
        report = NodeDriftReport(
            node_id=node.id,
            desired_version=desired_version,
            reported_version=reported_version if isinstance(reported_version, str) else None,
            severity=severity,
            drift={
                "in_sync": reported_version == desired_version,
                "locally_limited": locally_limited,
            },
            detected_at=datetime.now(UTC),
            remediated=False,
        )
        return await self._drift.add(report)

    def _severity(self, desired_version: str, reported_version: Any) -> DriftSeverity:
        if reported_version is None:
            return DriftSeverity.HIGH
        if reported_version == desired_version:
            return DriftSeverity.NONE
        return DriftSeverity.MEDIUM
