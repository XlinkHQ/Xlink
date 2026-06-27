#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

PANEL_URL = os.environ.get("XLINK_PANEL_URL", "http://localhost:8000").rstrip("/")
NODE_ID = os.environ.get("XLINK_NODE_ID", "")
TOKEN = os.environ.get("XLINK_AGENT_TOKEN", "")
INTERVAL = int(os.environ.get("XLINK_INTERVAL", "10"))
DRY_RUN = os.environ.get("XLINK_DRY_RUN", "") not in ("", "0", "false")

XRAY_CONFIG_PATH = os.environ.get("XLINK_XRAY_CONFIG", "/usr/local/etc/xray/config.json")
XRAY_RELOAD_CMD = os.environ.get("XLINK_XRAY_RELOAD", "systemctl restart xray")
XRAY_BIN = os.environ.get("XLINK_XRAY_BIN", "xray")
XRAY_API_ADDR = os.environ.get("XLINK_XRAY_API", "127.0.0.1:10085")
XRAY_ERROR_LOG = os.environ.get("XLINK_XRAY_ERROR_LOG", "/var/log/xray/error.log")
TLS_CERT_PATH = os.environ.get("XLINK_TLS_CERT", "/etc/ssl/xlink/cert.pem")
TLS_KEY_PATH = os.environ.get("XLINK_TLS_KEY", "/etc/ssl/xlink/key.pem")
WG_PRIVATE_KEY = os.environ.get("XLINK_WG_PRIVATE_KEY", "")
SINGBOX_API_ADDR = os.environ.get("XLINK_SINGBOX_API", "127.0.0.1:10086")
SINGBOX_V2RAY_API_ADDR = os.environ.get("XLINK_SINGBOX_V2RAY_API", "127.0.0.1:10088")
SINGBOX_PROTO_PATH = os.environ.get("XLINK_SINGBOX_PROTO", "/opt/xlink/v2ray_stats.proto")
_SINGBOX_V2RAY_ENV = os.environ.get("XLINK_SINGBOX_V2RAY_STATS", "auto").lower()
_v2ray_cache: bool | None = None


def _v2ray_enabled() -> bool:
    global _v2ray_cache
    if _SINGBOX_V2RAY_ENV in ("1", "true", "yes", "on"):
        return True
    if _SINGBOX_V2RAY_ENV in ("0", "false", "no", "off"):
        return False
    if _v2ray_cache is None:
        try:
            out = subprocess.run(
                ["sing-box", "version"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            _v2ray_cache = "with_v2ray_api" in out
        except (OSError, subprocess.SubprocessError):
            _v2ray_cache = False
    return _v2ray_cache


HYSTERIA_API_ADDR = os.environ.get("XLINK_HYSTERIA_API", "127.0.0.1:10087")
HYSTERIA_API_SECRET = os.environ.get("XLINK_HYSTERIA_API_SECRET", "xlink-stats")

AGENT_VERSION = "xlink-agent/1.2.0"
BASE = f"{PANEL_URL}/api/v1/agent/nodes/{NODE_ID}"
HEADERS = {"X-Agent-Token": TOKEN, "Content-Type": "application/json"}

_last_version: str | None = None
_last_active_kinds: set[str] = set()
_core_hash: dict[str, str] = {}
_usage_acc: dict[str, int] = {}
_over_users: set[str] = set()
_wg_prev: dict[str, tuple[int, int]] = {}
_wake = threading.Event()
_xray_core: dict = {}
_singbox_core: dict = {}
_hysteria_core: dict = {}
_pending_traffic: list[dict] = []
_log_offset: int = 0


def _xray_level(line: str) -> str:
    low = line.lower()
    if "[error]" in low or "[fatal]" in low:
        return "error"
    if "[warning]" in low or "[warn]" in low:
        return "warning"
    return "info"


def read_core_logs() -> list[str]:
    global _log_offset
    try:
        size = os.path.getsize(XRAY_ERROR_LOG)
    except OSError:
        return []
    if size < _log_offset:
        _log_offset = 0
    if size == _log_offset:
        return []
    try:
        with open(XRAY_ERROR_LOG, errors="replace") as fh:
            fh.seek(_log_offset)
            chunk = fh.read()
            _log_offset = fh.tell()
    except OSError:
        return []
    return [ln for ln in chunk.splitlines() if ln.strip()][-50:]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _log(msg: str) -> None:
    print(f"[{_now()}] {msg}", flush=True)


def _call(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:300]
    except Exception as exc:
        return 0, str(exc)


def _stream_settings(s: dict) -> dict:
    network = (s.get("network") or "tcp").lower()
    security = (s.get("security") or "none").lower()
    path = s.get("path") or "/"
    host = s.get("host") or ""
    stream: dict = {"network": network, "security": security}
    if network == "ws":
        ws: dict = {"path": path}
        if host:
            ws["headers"] = {"Host": host}
        stream["wsSettings"] = ws
    elif network == "httpupgrade":
        stream["httpupgradeSettings"] = {"path": path, **({"host": host} if host else {})}
    elif network == "grpc":
        stream["grpcSettings"] = {"serviceName": s.get("serviceName") or s.get("path") or ""}
    elif network == "xhttp":
        xh: dict = {"path": path, "mode": s.get("mode") or "auto"}
        if host:
            xh["host"] = host
        stream["xhttpSettings"] = xh
    elif network == "splithttp":
        stream["splithttpSettings"] = {"path": path, **({"host": host} if host else {})}
    elif network == "kcp":
        stream["kcpSettings"] = {}
    if security == "tls":
        tls: dict = {}
        if s.get("sni"):
            tls["serverName"] = s["sni"]
        if str(s.get("allowInsecure", "")).lower() in ("1", "true"):
            tls["allowInsecure"] = True
        stream["tlsSettings"] = tls
    elif security == "reality":
        stream["realitySettings"] = {
            "show": False,
            "dest": s.get("dest") or ((s.get("sni") or "www.microsoft.com") + ":443"),
            "serverNames": [s["sni"]] if s.get("sni") else [],
            "privateKey": s.get("privateKey", ""),
            "shortIds": [s.get("shortId", "")],
        }
    return stream


def _client_entry(protocol: str, cid: str, email: str, s: dict) -> dict:
    if protocol in ("vless",):
        c = {"id": cid, "email": email}
        if s.get("flow"):
            c["flow"] = s["flow"]
        return c
    if protocol in ("vmess",):
        return {"id": cid, "email": email, "alterId": int(s.get("alterId", 0) or 0)}
    if protocol in ("trojan",):
        return {"password": cid, "email": email}
    if protocol in ("shadowsocks",):
        return {"password": cid, "email": email, "method": s.get("method", "aes-256-gcm")}
    return {"id": cid, "email": email}


def _client_id(cl: dict) -> str:
    creds = cl.get("credentials") or {}
    s = cl.get("settings") or {}
    protocol = (cl.get("protocol") or "vless").lower()
    if protocol in ("trojan", "shadowsocks", "hysteria2", "hysteria", "tuic"):
        secret = creds.get("password") or s.get("password")
    else:
        secret = creds.get("uuid") or s.get("uuid")
    return str(secret or cl.get("provider_client_id") or cl.get("assignment_id"))


def build_xray_config(clients: list[dict]) -> dict:
    inbounds: dict[tuple, dict] = {}
    for cl in clients:
        protocol = cl.get("protocol", "vless")
        s = cl.get("settings") or {}
        port = int(s.get("port", 443) or 443)
        key = (port, protocol, json.dumps(_stream_settings(s), sort_keys=True))
        cid = _client_id(cl)
        email = cl.get("assignment_id")
        if key not in inbounds:
            settings: dict = {"clients": []}
            if protocol == "vless":
                settings["decryption"] = "none"
            if protocol == "shadowsocks":
                settings["method"] = s.get("method", "aes-256-gcm")
            if isinstance(s.get("fallbacks"), list) and protocol in ("vless", "trojan"):
                settings["fallbacks"] = s["fallbacks"]
            network = (s.get("network") or "tcp").lower()
            inbounds[key] = {
                "tag": f"in-{port}-{protocol}-{network}-{len(inbounds)}",
                "listen": "0.0.0.0",
                "port": port,
                "protocol": protocol,
                "settings": settings,
                "streamSettings": _stream_settings(s),
                "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
            }
        inbounds[key]["settings"]["clients"].append(_client_entry(protocol, cid, email, s))

    api_inbound = {
        "tag": "api",
        "listen": XRAY_API_ADDR.split(":")[0],
        "port": int(XRAY_API_ADDR.split(":")[1]),
        "protocol": "dokodemo-door",
        "settings": {"address": "127.0.0.1"},
    }
    api_rule = {"type": "field", "inboundTag": ["api"], "outboundTag": "api"}
    core = _xray_core if isinstance(_xray_core, dict) else {}
    config: dict = {
        "log": core.get("log", {"loglevel": "warning", "error": XRAY_ERROR_LOG}),
        "stats": {},
        "policy": core.get(
            "policy",
            {
                "levels": {"0": {"statsUserUplink": True, "statsUserDownlink": True}},
                "system": {"statsInboundUplink": True, "statsInboundDownlink": True},
            },
        ),
        "api": {"tag": "api", "services": ["StatsService"]},
        "inbounds": [api_inbound, *inbounds.values()],
        "outbounds": core.get(
            "outbounds", [{"protocol": "freedom", "settings": {"domainStrategy": "UseIP"}}]
        ),
    }
    if core.get("dns"):
        config["dns"] = core["dns"]
    routing = dict(core.get("routing", {}))
    routing["rules"] = [api_rule, *[r for r in routing.get("rules", []) if r != api_rule]]
    config["routing"] = routing
    return config


def _singbox_user(protocol: str, cid: str, email: str, s: dict) -> dict:
    if protocol == "vless":
        u = {"uuid": cid, "name": email}
        if s.get("flow"):
            u["flow"] = s["flow"]
        return u
    if protocol == "vmess":
        return {"uuid": cid, "name": email, "alterId": int(s.get("alterId", 0) or 0)}
    if protocol == "tuic":
        return {"uuid": cid, "password": cid, "name": email}
    return {"password": cid, "name": email}


def _singbox_tls(s: dict) -> dict:
    tls = {"enabled": True, "certificate_path": TLS_CERT_PATH, "key_path": TLS_KEY_PATH}
    if s.get("sni"):
        tls["server_name"] = s["sni"]
    return tls


def _singbox_transport(s: dict) -> dict | None:
    network = (s.get("network") or "tcp").lower()
    if network in ("ws", "httpupgrade"):
        return {"type": network, "path": s.get("path") or "/"}
    if network == "grpc":
        return {"type": "grpc", "service_name": s.get("path") or ""}
    return None


_SB_TRANSPORT_OK = {"vless", "vmess", "trojan"}
_SB_TLS_OK = {"vless", "vmess", "trojan", "hysteria2", "tuic"}
_SB_TLS_MANDATORY = {"hysteria2", "tuic"}


def build_singbox_config(clients: list[dict]) -> dict:
    inbounds: dict[tuple, dict] = {}
    for cl in clients:
        protocol = cl.get("protocol", "vless")
        s = cl.get("settings") or {}
        port = int(s.get("port", 443) or 443)
        secure = (s.get("security") or "none").lower() in ("tls", "reality")
        key = (port, protocol, secure, json.dumps(_singbox_transport(s) or {}, sort_keys=True))
        cid = _client_id(cl)
        if key not in inbounds:
            ib: dict = {
                "type": protocol,
                "tag": f"in-{port}-{protocol}-{len(inbounds)}",
                "listen": "0.0.0.0",
                "listen_port": port,
                "users": [],
            }
            if protocol == "shadowsocks":
                ib["method"] = s.get("method", "aes-256-gcm")
            else:
                tls_required = protocol in _SB_TLS_MANDATORY
                if (secure or tls_required) and protocol in _SB_TLS_OK:
                    ib["tls"] = _singbox_tls(s)
                transport = _singbox_transport(s)
                if transport and protocol in _SB_TRANSPORT_OK:
                    ib["transport"] = transport
            inbounds[key] = ib
        inbounds[key]["users"].append(_singbox_user(protocol, cid, cl.get("assignment_id"), s))
    core = _singbox_core if isinstance(_singbox_core, dict) else {}
    user_names = sorted({u["name"] for ib in inbounds.values() for u in ib["users"] if u.get("name")})
    experimental: dict = {}
    if _v2ray_enabled():
        experimental["v2ray_api"] = {
            "listen": SINGBOX_V2RAY_API_ADDR,
            "stats": {"enabled": True, "users": user_names},
        }
    else:
        experimental["clash_api"] = {"external_controller": SINGBOX_API_ADDR}
    config: dict = {
        "log": core.get("log", {"level": "warn"}),
        "inbounds": list(inbounds.values()),
        "outbounds": core.get("outbounds", [{"type": "direct"}]),
        "experimental": core.get("experimental", experimental),
    }
    for key_name in ("dns", "route", "ntp"):
        if core.get(key_name):
            config[key_name] = core[key_name]
    return config


def build_wireguard_config(clients: list[dict]) -> str:
    s0 = (clients[0].get("settings") or {}) if clients else {}
    port = int(s0.get("port", 51820) or 51820)
    if not (1 <= port <= 65535):
        port = 51820
    priv = str(s0.get("privateKey") or s0.get("private_key") or WG_PRIVATE_KEY or "").strip()
    if not priv:
        raise RuntimeError("wireguard: no private key in settings or XLINK_WG_PRIVATE_KEY")
    addr = str(s0.get("address") or "10.8.0.1/24").strip()
    lines = [
        "[Interface]",
        f"ListenPort = {port}",
        f"PrivateKey = {priv}",
        f"Address = {addr}",
    ]
    for i, cl in enumerate(clients, start=2):
        creds = cl.get("credentials") or {}
        pub = creds.get("public_key")
        if not pub:
            continue
        addr = str(creds.get("address") or f"10.8.0.{i}")
        ip = addr.split("/")[0].strip()
        if not ip or ip == "10.8.0.1":
            ip = f"10.8.0.{i}"
        lines += ["", "[Peer]", f"PublicKey = {pub}", f"AllowedIPs = {ip}/32"]
    return "\n".join(lines) + "\n"


def build_hysteria_config(clients: list[dict]) -> dict:
    s0 = (clients[0].get("settings") or {}) if clients else {}
    port = int(s0.get("port", 443) or 443)
    passwords = [_client_id(c) for c in clients]
    core = _hysteria_core if isinstance(_hysteria_core, dict) else {}
    config = {
        "listen": f":{port}",
        "tls": {"cert": TLS_CERT_PATH, "key": TLS_KEY_PATH},
        "auth": {"type": "userpass", "userpass": {p: p for p in passwords}},
        "trafficStats": {"listen": HYSTERIA_API_ADDR, "secret": HYSTERIA_API_SECRET},
    }
    for c in clients:
        cs = c.get("settings") or {}
        obfs_pw = cs.get("obfsPassword") or cs.get("obfs_password")
        if cs.get("obfs") and obfs_pw:
            config["obfs"] = {"type": "salamander", "salamander": {"password": str(obfs_pw)}}
            break
    for key_name in ("acl", "outbounds", "bandwidth", "masquerade", "log", "resolver", "sniff"):
        if core.get(key_name):
            config[key_name] = core[key_name]
    return config


CORES = {
    "xray": {
        "builder": build_xray_config,
        "fmt": "json",
        "path": os.environ.get("XLINK_XRAY_CONFIG", "/usr/local/etc/xray/config.json"),
        "reload": os.environ.get("XLINK_XRAY_RELOAD", "systemctl restart xray"),
        "validate": f"{XRAY_BIN} run -test -c {{path}}",
        "service": os.environ.get("XLINK_XRAY_SERVICE", "xray"),
    },
    "sing-box": {
        "builder": build_singbox_config,
        "fmt": "json",
        "path": os.environ.get("XLINK_SINGBOX_CONFIG", "/etc/sing-box/config.json"),
        "reload": os.environ.get("XLINK_SINGBOX_RELOAD", "systemctl restart sing-box"),
        "validate": "sing-box check -c {path}",
        "service": os.environ.get("XLINK_SINGBOX_SERVICE", "sing-box"),
    },
    "wireguard": {
        "builder": build_wireguard_config,
        "fmt": "text",
        "path": os.environ.get("XLINK_WG_CONFIG", "/etc/wireguard/wg0.conf"),
        "reload": os.environ.get(
            "XLINK_WG_RELOAD",
            "if ip link show wg0 >/dev/null 2>&1; then "
            "wg syncconf wg0 <(wg-quick strip wg0) || "
            "{ (wg-quick down wg0 2>/dev/null; ip link delete wg0 2>/dev/null); wg-quick up wg0; }; "
            "else wg-quick up wg0; fi",
        ),
        "validate": None,
        "service": os.environ.get("XLINK_WG_SERVICE", "wg-quick@wg0"),
    },
    "hysteria": {
        "builder": build_hysteria_config,
        "fmt": "json",
        "path": os.environ.get("XLINK_HYSTERIA_CONFIG", "/etc/hysteria/config.json"),
        "reload": os.environ.get("XLINK_HYSTERIA_RELOAD", "systemctl restart hysteria-server"),
        "validate": None,
        "service": os.environ.get("XLINK_HYSTERIA_SERVICE", "hysteria-server"),
    },
}

WG_INTERFACE = os.environ.get("XLINK_WG_INTERFACE", "wg0")


def _systemd_active(service: str) -> bool | None:
    try:
        rc = subprocess.run(
            ["systemctl", "is-active", "--quiet", service],
            timeout=5,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return rc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return None


def _xray_api_ok(retries: int = 6, delay: float = 0.5) -> bool:
    import socket

    host, _, port = XRAY_API_ADDR.rpartition(":")
    host = host or "127.0.0.1"
    try:
        port_i = int(port)
    except ValueError:
        return False
    for attempt in range(retries):
        try:
            with socket.create_connection((host, port_i), timeout=3):
                return True
        except OSError:
            if attempt < retries - 1:
                time.sleep(delay)
    return False


def check_provider_health(active_kinds: set[str]) -> dict[str, str]:
    status: dict[str, str] = {}
    for kind in active_kinds:
        core = CORES.get(kind)
        if core is None:
            continue
        if not _core_installed(kind, core):
            status[kind] = "not_installed"
            continue
        if kind == "xray":
            healthy = _xray_api_ok()
            if not healthy:
                active = _systemd_active(core.get("service", "xray"))
                if active:
                    healthy = True
        else:
            active = _systemd_active(core.get("service", ""))
            healthy = os.path.exists(core["path"]) if active is None else active
        status[kind] = "healthy" if healthy else "unhealthy"
    return status


def _wireguard_traffic(clients: list[dict]) -> list[dict]:
    try:
        out = subprocess.check_output(
            ["wg", "show", WG_INTERFACE, "transfer"],
            timeout=8,
            stderr=subprocess.DEVNULL,
        ).decode()
    except (OSError, subprocess.SubprocessError):
        return []
    peer_to_assignment = {}
    for cl in clients:
        pub = (cl.get("credentials") or {}).get("public_key")
        if pub:
            peer_to_assignment[pub] = cl.get("assignment_id")
    ts = _now()
    samples = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        peer, rx, tx = parts
        assignment = peer_to_assignment.get(peer)
        if assignment is None:
            continue
        rx_b, tx_b = int(rx or 0), int(tx or 0)
        prev_rx, prev_tx = _wg_prev.get(peer, (0, 0))
        d_rx = rx_b - prev_rx if rx_b >= prev_rx else rx_b
        d_tx = tx_b - prev_tx if tx_b >= prev_tx else tx_b
        _wg_prev[peer] = (rx_b, tx_b)
        if d_rx or d_tx:
            samples.append(
                {
                    "assignment_id": assignment,
                    "upload_bytes": d_rx,
                    "download_bytes": d_tx,
                    "collected_at": ts,
                }
            )
    return samples


def _write(path: str, built, fmt: str) -> None:
    with open(path, "w") as fh:
        if fmt == "json":
            json.dump(built, fh, indent=2)
        else:
            fh.write(built)


def _run(cmd: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            executable="/bin/bash",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
            text=True,
        )
        return proc.returncode, (proc.stdout or "").strip()
    except FileNotFoundError:
        return 127, "command not found"
    except subprocess.SubprocessError as exc:
        return 1, str(exc)


def _validate_candidate(kind: str, validate: str, tmp: str) -> bool:
    rc, out = _run(validate.format(path=tmp))
    if rc == 0:
        return True
    if rc == 127:
        _log(f"{kind}: validator unavailable ({validate.split()[0]}); skipping validation")
        return True
    tail = out.splitlines()[-3:] if out else []
    _log(f"{kind}: candidate config INVALID (rc={rc}) — keeping current config. {' | '.join(tail)}")
    return False


def _core_installed(kind: str, core: dict) -> bool:
    service = core.get("service", "")
    if service:
        rc, _ = _run(f"systemctl cat {service} >/dev/null 2>&1")
        if rc == 0:
            return True
    binary = {"xray": XRAY_BIN, "sing-box": "sing-box", "hysteria": "hysteria"}.get(kind)
    if binary:
        rc, _ = _run(f"command -v {binary} >/dev/null 2>&1")
        return rc == 0
    if kind == "wireguard":
        rc, _ = _run("command -v wg >/dev/null 2>&1")
        return rc == 0
    return False


def apply_one(kind: str, core: dict, core_clients: list[dict]) -> bool:
    if not _core_installed(kind, core):
        if core_clients:
            _log(f"{kind}: not installed on this node — skipping {len(core_clients)} client(s)")
        return True
    path = core["path"]
    root, ext = os.path.splitext(path)
    tmp = f"{root}.tmp{ext}"
    backup = f"{root}.bak{ext}"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    _write(tmp, core["builder"](core_clients), core["fmt"])

    validate = core.get("validate")
    if validate and not _validate_candidate(kind, validate, tmp):
        with contextlib.suppress(OSError):
            os.remove(tmp)
        return False

    if os.path.exists(path):
        shutil.copy2(path, backup)
    os.replace(tmp, path)

    rc, out = _run(core["reload"])
    if rc == 0:
        _log(f"applied {kind} ({len(core_clients)} clients), reloaded")
        return True
    tail = out.splitlines()[-3:] if out else []
    _log(f"{kind}: reload FAILED (rc={rc}: {core['reload']}). {' | '.join(tail)}")
    if os.path.exists(backup):
        os.replace(backup, path)
        _run(core["reload"])
        _log(f"{kind}: ROLLED BACK to previous config")
    return False


def _effective_core(cl: dict) -> str:
    return cl.get("provider_kind", "xray")


def apply_config(clients: list[dict], version: str) -> set[str]:
    global _last_version, _last_active_kinds
    by_core: dict[str, list[dict]] = {}
    for cl in clients:
        by_core.setdefault(_effective_core(cl), []).append(cl)
    active_kinds = {k for k in by_core if k in CORES}

    drained = (_last_active_kinds - active_kinds) & set(CORES)
    if _last_version is None and "xray" in CORES:
        drained = drained | {"xray"}
    for kind in drained:
        by_core.setdefault(kind, [])

    ok = True
    for kind, core_clients in by_core.items():
        core = CORES.get(kind)
        if core is None:
            _log(f"unsupported core '{kind}' — skipping {len(core_clients)} client(s)")
            continue
        try:
            built = core["builder"](core_clients)
        except Exception as exc:
            _log(f"{kind} build error: {exc}")
            ok = False
            continue
        body = json.dumps(built, sort_keys=True) if core["fmt"] == "json" else str(built)
        digest = hashlib.sha256(body.encode()).hexdigest()
        if _core_hash.get(kind) == digest:
            continue
        if DRY_RUN:
            _log(f"[dry-run] {kind}: {len(core_clients)} client(s)")
            _core_hash[kind] = digest
            continue
        try:
            if apply_one(kind, core, core_clients):
                _core_hash[kind] = digest
            else:
                ok = False
        except Exception as exc:
            ok = False
            _log(f"{kind} apply error: {exc}")
    if ok:
        _last_version = version
        _last_active_kinds = active_kinds
    return active_kinds


def _xray_traffic() -> list[dict]:
    try:
        out = subprocess.check_output(
            [
                XRAY_BIN,
                "api",
                "statsquery",
                f"--server={XRAY_API_ADDR}",
                "-pattern",
                "user>>>",
                "-reset",
            ],
            timeout=10,
            stderr=subprocess.DEVNULL,
        )
        data = json.loads(out or b"{}")
    except Exception as exc:
        _log(f"xray stats query failed: {exc}")
        return []

    usage: dict[str, dict[str, int]] = {}
    for stat in data.get("stat", []):
        parts = stat.get("name", "").split(">>>")
        if len(parts) != 4:
            continue
        email, direction = parts[1], parts[3]
        value = int(stat.get("value", 0) or 0)
        slot = usage.setdefault(email, {"up": 0, "down": 0})
        slot["up" if direction == "uplink" else "down"] += value

    ts = _now()
    return [
        {
            "assignment_id": email,
            "upload_bytes": v["up"],
            "download_bytes": v["down"],
            "collected_at": ts,
        }
        for email, v in usage.items()
        if v["up"] or v["down"]
    ]


def _http_get_json(url: str, headers: dict | None = None, timeout: int = 8):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read() or b"{}")


def _hysteria_traffic() -> list[dict]:
    try:
        data = _http_get_json(
            f"http://{HYSTERIA_API_ADDR}/traffic?clear=1",
            headers={"Authorization": HYSTERIA_API_SECRET},
        )
    except Exception as exc:
        _log(f"hysteria stats query failed: {exc}")
        return []
    ts = _now()
    out = []
    for user, v in (data or {}).items():
        up = int(v.get("tx", 0) or 0)
        down = int(v.get("rx", 0) or 0)
        if up or down:
            out.append(
                {
                    "assignment_id": user,
                    "upload_bytes": up,
                    "download_bytes": down,
                    "collected_at": ts,
                }
            )
    return out


def _singbox_traffic() -> list[dict]:
    try:
        out = subprocess.check_output(
            [
                "grpcurl",
                "-plaintext",
                "-import-path",
                os.path.dirname(SINGBOX_PROTO_PATH) or ".",
                "-proto",
                os.path.basename(SINGBOX_PROTO_PATH),
                "-d",
                '{"reset": true}',
                SINGBOX_V2RAY_API_ADDR,
                "v2ray.core.app.stats.command.StatsService/QueryStats",
            ],
            timeout=10,
            stderr=subprocess.STDOUT,
        )
        data = json.loads(out or b"{}")
    except Exception as exc:
        _log(f"sing-box stats query failed: {exc}")
        return []

    usage: dict[str, dict[str, int]] = {}
    for stat in data.get("stat", []) or []:
        parts = stat.get("name", "").split(">>>")
        if len(parts) != 4:
            continue
        email, direction = parts[1], parts[3]
        value = int(stat.get("value", 0) or 0)
        slot = usage.setdefault(email, {"up": 0, "down": 0})
        slot["up" if direction == "uplink" else "down"] += value

    ts = _now()
    return [
        {
            "assignment_id": email,
            "upload_bytes": v["up"],
            "download_bytes": v["down"],
            "collected_at": ts,
        }
        for email, v in usage.items()
        if v["up"] or v["down"]
    ]


def collect_traffic(active_kinds: set[str], clients: list[dict] | None = None) -> list[dict]:
    if DRY_RUN:
        return []
    samples: list[dict] = []
    if "xray" in active_kinds:
        samples += _xray_traffic()
    if "wireguard" in active_kinds:
        samples += _wireguard_traffic(clients or [])
    if "hysteria" in active_kinds:
        samples += _hysteria_traffic()
    if "sing-box" in active_kinds and _v2ray_enabled():
        samples += _singbox_traffic()
    return samples


def read_metrics() -> tuple[float, float]:
    cpu = 0.0
    mem = 0.0
    with contextlib.suppress(OSError, AttributeError):
        cpu = round(min(100.0, (os.getloadavg()[0] / (os.cpu_count() or 1)) * 100.0), 1)
    with contextlib.suppress(OSError, ValueError):
        info: dict[str, int] = {}
        with open("/proc/meminfo") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                if rest:
                    info[key] = int(rest.strip().split()[0])
        total, avail = info.get("MemTotal", 0), info.get("MemAvailable", 0)
        if total:
            mem = round((1 - avail / total) * 100.0, 1)
    return cpu, mem


def _local_enforce(clients: list[dict], samples: list[dict]) -> list[dict]:
    global _over_users
    asg_user = {c.get("assignment_id"): c.get("user_id") for c in clients}
    user_limit: dict[str, int] = {}
    user_base: dict[str, int] = {}
    for c in clients:
        uid = c.get("user_id")
        if not uid:
            continue
        lim = c.get("data_limit_bytes")
        if lim:
            user_limit[uid] = int(lim)
        user_base[uid] = max(user_base.get(uid, 0), int(c.get("used_bytes", 0) or 0))
    for s in samples:
        uid = asg_user.get(s.get("assignment_id"))
        if uid is None:
            continue
        used = int(s.get("upload_bytes", 0) or 0) + int(s.get("download_bytes", 0) or 0)
        _usage_acc[uid] = _usage_acc.get(uid, 0) + used
    over = {
        uid
        for uid, lim in user_limit.items()
        if user_base.get(uid, 0) + _usage_acc.get(uid, 0) >= lim
    }
    if over != _over_users:
        newly = over - _over_users
        if newly:
            _log(f"local limit reached for {len(newly)} user(s), dropping")
        _over_users = over
    if not over:
        return clients
    return [c for c in clients if c.get("user_id") not in over]


def cycle() -> None:
    sc, cfg = _call("GET", "/config")
    if sc != 200:
        _log(f"config pull failed ({sc}): {cfg}")
        return
    version = cfg.get("config_version")
    conf = cfg.get("config") or {}
    clients = conf.get("clients", [])
    global _xray_core, _singbox_core, _hysteria_core
    cores = conf.get("core_templates") or {}
    _xray_core = cores.get("xray") or {}
    _singbox_core = cores.get("sing-box") or {}
    _hysteria_core = cores.get("hysteria") or {}
    _log(f"pulled config v={version} clients={len(clients)}")

    kinds_present = {_effective_core(c) for c in clients} & set(CORES)
    pre_samples: list[dict] = []
    active_kinds: set[str] = set()
    try:
        pre_samples = collect_traffic(kinds_present, clients) if not DRY_RUN else []
        effective = _local_enforce(clients, pre_samples)
        if len(effective) != len(clients):
            version = f"{version}-local{len(effective)}"
        active_kinds = apply_config(effective, version)
    except Exception as exc:
        _log(f"apply cycle error (continuing to report state): {exc}")
        active_kinds = {_effective_core(c) for c in clients} & set(CORES)

    cpu, mem = read_metrics()
    provider_status = check_provider_health(active_kinds) if not DRY_RUN else {}
    unhealthy = [k for k, v in provider_status.items() if v != "healthy"]
    if unhealthy:
        _log(f"provider health: UNHEALTHY {unhealthy} (status={provider_status})")
    _call(
        "POST",
        "/state",
        {
            "config_version": version,
            "agent_version": AGENT_VERSION,
            "applied": {"config_version": version},
            "provider_status": provider_status,
        },
    )
    if provider_status:
        _call(
            "POST",
            "/provider-health",
            {
                "checks": [
                    {"provider_name": kind, "status": st, "detail": None, "latency_ms": None}
                    for kind, st in provider_status.items()
                ],
            },
        )

    global _pending_traffic
    samples = _pending_traffic + pre_samples
    if samples:
        batch = f"{NODE_ID}-{int(time.time())}"
        sc, _ = _call("POST", "/traffic", {"batch_id": batch, "samples": samples})
        if sc == 200:
            _pending_traffic = []
            _log(f"reported traffic for {len(samples)} client(s) ({sc})")
        else:
            _pending_traffic = samples[-5000:]
            _log(f"traffic report failed ({sc}); buffered {len(_pending_traffic)} sample(s)")

    ts = _now()
    _call(
        "POST",
        "/metrics",
        {
            "samples": [
                {"name": "cpu_percent", "value": cpu, "observed_at": ts},
                {"name": "memory_percent", "value": mem, "observed_at": ts},
                {"name": "clients", "value": float(len(clients)), "observed_at": ts},
            ]
        },
    )
    core_lines = read_core_logs()
    if core_lines:
        _call(
            "POST",
            "/logs",
            {
                "lines": [
                    {"level": _xray_level(ln), "message": ln, "observed_at": ts}
                    for ln in core_lines
                ]
            },
        )


def sse_listener() -> None:
    url = f"{BASE}/events"
    while True:
        try:
            req = urllib.request.Request(
                url, headers={"X-Agent-Token": TOKEN, "Accept": "text/event-stream"}
            )
            with urllib.request.urlopen(req, timeout=None) as resp:
                for raw in resp:
                    if raw.decode("utf-8", "ignore").startswith("data:"):
                        _wake.set()
        except Exception:
            time.sleep(5)


def main() -> int:
    if not NODE_ID or not TOKEN:
        print("Set XLINK_NODE_ID and XLINK_AGENT_TOKEN.", file=sys.stderr)
        return 2
    _log(f"xlink-agent → {PANEL_URL} node={NODE_ID} every {INTERVAL}s dry_run={DRY_RUN}")
    if not DRY_RUN:
        with contextlib.suppress(OSError):
            os.makedirs(os.path.dirname(XRAY_ERROR_LOG) or ".", exist_ok=True)
    threading.Thread(target=sse_listener, daemon=True).start()
    while True:
        try:
            cycle()
        except Exception as exc:
            _log(f"cycle error: {exc}")
        _wake.wait(timeout=INTERVAL)
        _wake.clear()


if __name__ == "__main__":
    raise SystemExit(main())
