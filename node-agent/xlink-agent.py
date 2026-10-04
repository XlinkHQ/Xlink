#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime

PANEL_URL = os.environ.get("XLINK_PANEL_URL", "http://localhost:8000").rstrip("/")
NODE_ID = os.environ.get("XLINK_NODE_ID", "")
TOKEN = os.environ.get("XLINK_AGENT_TOKEN", "")
INTERVAL = int(os.environ.get("XLINK_INTERVAL", "10"))
FAST_INTERVAL = int(os.environ.get("XLINK_FAST_ENFORCE_INTERVAL", "3"))
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
        if not _v2ray_cache:
            _log(
                "sing-box built without v2ray_api tag — per-user traffic stats "
                "unavailable; usage will report as zero for sing-box users"
            )
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
_last_clients: list[dict] = []
_last_kinds: set[str] = set()
_last_effective_version: str | None = None
_enforce_lock = threading.Lock()
_wg_prev: dict[str, tuple[int, int]] = {}
_wake = threading.Event()
_xray_core: dict = {}
_singbox_core: dict = {}
_hysteria_core: dict = {}
_log_offset: int = 0

WAL_PATH = os.environ.get("XLINK_TRAFFIC_WAL", "/var/lib/xlink/traffic.wal")
_WAL_MAX = 5000
_wal_lock = threading.Lock()
_wal_carryover: list[dict] = []

_WAL_MAX_AGE_DAYS = max(1, min(60, int(os.environ.get("XLINK_WAL_MAX_AGE_DAYS", "30"))))
_WAL_MAX_AGE_SECONDS = _WAL_MAX_AGE_DAYS * 86400


def _sample_age_seconds(sample: dict, now: float) -> float | None:
    ts = sample.get("collected_at")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return now - dt.timestamp()


def _drop_stale_wal(samples: list[dict]) -> list[dict]:
    if not samples:
        return samples
    now = time.time()
    kept: list[dict] = []
    dropped = 0
    dropped_bytes = 0
    for s in samples:
        age = _sample_age_seconds(s, now)
        if age is not None and age > _WAL_MAX_AGE_SECONDS:
            dropped += 1
            dropped_bytes += int(s.get("upload_bytes", 0) or 0) + int(
                s.get("download_bytes", 0) or 0
            )
            continue
        kept.append(s)
    if dropped:
        _log(
            f"wal: dropped {dropped} stale entr{'y' if dropped == 1 else 'ies'} "
            f"older than {_WAL_MAX_AGE_DAYS}d ({dropped_bytes} bytes lost) — "
            "would exceed panel ledger retention"
        )
    return kept


def _wal_append(samples: list[dict]) -> None:
    with _wal_lock:
        global _wal_carryover
        batch = _wal_carryover + list(samples)
        if not batch:
            return
        try:
            os.makedirs(os.path.dirname(WAL_PATH) or ".", exist_ok=True)
            with open(WAL_PATH, "a") as fh:
                for s in batch:
                    fh.write(json.dumps(s) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            _wal_carryover = []
        except OSError as exc:
            _wal_carryover = batch[-_WAL_MAX:]
            _log(f"wal append failed, {len(_wal_carryover)} samples held in memory: {exc}")


_WAL_INFLIGHT = WAL_PATH + ".inflight"


def _read_wal_file(path: str) -> list[dict]:
    out: list[dict] = []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    except FileNotFoundError:
        return []
    except OSError as exc:
        _log(f"wal read failed: {exc}")
    return out


def _wal_rotate() -> list[dict]:
    with _wal_lock:
        pending = _read_wal_file(_WAL_INFLIGHT)
        try:
            if os.path.exists(WAL_PATH):
                if pending:
                    with open(WAL_PATH) as fh, open(_WAL_INFLIGHT, "a") as out:
                        out.write(fh.read())
                    os.remove(WAL_PATH)
                else:
                    os.replace(WAL_PATH, _WAL_INFLIGHT)
        except OSError as exc:
            _log(f"wal rotate failed: {exc}")
        pending = _read_wal_file(_WAL_INFLIGHT)
        fresh = _drop_stale_wal(pending)
        if len(fresh) != len(pending):
            with contextlib.suppress(OSError):
                if fresh:
                    tmp = _WAL_INFLIGHT + ".tmp"
                    with open(tmp, "w") as fh:
                        for s in fresh:
                            fh.write(json.dumps(s) + "\n")
                        fh.flush()
                        os.fsync(fh.fileno())
                    os.replace(tmp, _WAL_INFLIGHT)
                elif os.path.exists(_WAL_INFLIGHT):
                    os.remove(_WAL_INFLIGHT)
        return fresh[:_WAL_MAX]


def _wal_commit(delivered: int) -> None:
    with _wal_lock, contextlib.suppress(OSError):
        if not os.path.exists(_WAL_INFLIGHT):
            return
        remaining = _read_wal_file(_WAL_INFLIGHT)[delivered:]
        if not remaining:
            os.remove(_WAL_INFLIGHT)
            return
        tmp = _WAL_INFLIGHT + ".tmp"
        with open(tmp, "w") as fh:
            for s in remaining:
                fh.write(json.dumps(s) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, _WAL_INFLIGHT)


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
    return [ln for ln in chunk.splitlines() if ln.strip()][-500:]


def _journal_level(line: str) -> str:
    low = line.lower()
    if "error" in low or "fatal" in low or "panic" in low:
        return "error"
    if "warn" in low:
        return "warning"
    return "info"


def read_service_logs(service: str) -> list[str]:
    state_dir = os.path.dirname(WAL_PATH) or "/var/lib/xlink"
    with contextlib.suppress(OSError):
        os.makedirs(state_dir, exist_ok=True)
    cur = os.path.join(state_dir, f".journal-{service.replace('@', '_').replace('/', '_')}")
    args = [
        "journalctl",
        "-u",
        service,
        "--no-pager",
        "-o",
        "cat",
        "--cursor-file",
        cur,
    ]
    if not os.path.exists(cur):
        args += ["-n", "50"]
    try:
        out = subprocess.run(
            args, timeout=8, capture_output=True, text=True, errors="replace"
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    return [ln for ln in out.stdout.splitlines() if ln.strip()][-50:]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _log(msg: str) -> None:
    print(f"[{_now()}] {msg}", flush=True)


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _http_call(method: str, path: str, body: dict | None = None, known_version: str | None = None):
    data = json.dumps(body).encode() if body is not None else None
    headers = HEADERS
    if known_version:
        headers = {**HEADERS, "If-None-Match": f'"{known_version}"'}
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:300]
    except Exception as exc:
        return 0, str(exc)


GRPC_ENABLED = os.environ.get("XLINK_GRPC", "0") in ("1", "true", "True")
GRPC_ADDR = os.environ.get("XLINK_GRPC_ADDR", "")
GRPC_TLS = os.environ.get("XLINK_GRPC_TLS", "0") in ("1", "true", "True")
GRPC_TLS_CA = os.environ.get("XLINK_GRPC_TLS_CA", "")
GRPC_TLS_CERT = os.environ.get("XLINK_GRPC_TLS_CERT", "")
GRPC_TLS_KEY = os.environ.get("XLINK_GRPC_TLS_KEY", "")

_grpc = None
_grpc_stub = None
_grpc_pb = None
_grpc_channel = None


def _grpc_ready() -> bool:
    global _grpc, _grpc_stub, _grpc_pb, _grpc_channel
    if not GRPC_ENABLED:
        return False
    if _grpc_stub is not None:
        return True
    try:
        import grpc  # type: ignore

        from app.agent.grpc import agent_pb2 as pb  # type: ignore
        from app.agent.grpc import agent_pb2_grpc as pbg  # type: ignore
    except Exception as exc:
        _log(f"grpc unavailable, falling back to HTTP: {exc}")
        return False
    addr = GRPC_ADDR or (PANEL_URL.split("://", 1)[-1].split(":", 1)[0] + ":50051")
    try:
        if GRPC_TLS:
            def _read_bytes(p):
                if not p:
                    return None
                with open(p, "rb") as fh:
                    return fh.read()

            ca = _read_bytes(GRPC_TLS_CA)
            cert = _read_bytes(GRPC_TLS_CERT)
            key = _read_bytes(GRPC_TLS_KEY)
            creds = grpc.ssl_channel_credentials(
                root_certificates=ca, private_key=key, certificate_chain=cert
            )
            channel = grpc.secure_channel(addr, creds)
        else:
            channel = grpc.insecure_channel(addr)
        _grpc = grpc
        _grpc_pb = pb
        _grpc_channel = channel
        _grpc_stub = pbg.NodeAgentStub(channel)
        _log(f"grpc transport → {addr} tls={GRPC_TLS}")
        return True
    except Exception as exc:
        _log(f"grpc channel init failed, HTTP fallback: {exc}")
        return False


def _grpc_meta():
    return (("x-agent-token", TOKEN),)


def _grpc_ms(iso: str) -> int:
    try:
        return int(datetime.fromisoformat(iso).timestamp() * 1000)
    except Exception:
        return int(time.time() * 1000)


def _grpc_call(path: str, body: dict | None, known_version: str | None = None):
    global _grpc_stub, _grpc_channel
    pb = _grpc_pb
    stub = _grpc_stub
    md = _grpc_meta()
    try:
        if path == "/config":
            resp = stub.GetConfig(
                pb.ConfigRequest(node_id=NODE_ID, known_version=known_version or ""),
                metadata=md,
                timeout=15,
            )
            return 200, {
                "node_id": resp.node_id,
                "config_version": resp.config_version,
                "config": json.loads(resp.config_json or "{}"),
                "assignment_count": resp.assignment_count,
            }
        if path == "/traffic":
            samples = [
                pb.TrafficSample(
                    assignment_id=s["assignment_id"],
                    upload_bytes=int(s["upload_bytes"]),
                    download_bytes=int(s["download_bytes"]),
                    collected_at_unix_ms=_grpc_ms(s["collected_at"]),
                )
                for s in body.get("samples", [])
            ]
            batch = pb.TrafficBatch(node_id=NODE_ID, batch_id=body["batch_id"], samples=samples)
            acks = list(stub.StreamTraffic(iter([batch]), metadata=md, timeout=30))
            if any(a.batch_id == body["batch_id"] for a in acks):
                return 200, {}
            return 0, "no ack for traffic batch"
        if path == "/metrics":
            batch = pb.MetricBatch(
                node_id=NODE_ID,
                samples=[
                    pb.MetricSample(name=s["name"], value=float(s["value"]), observed_at_unix_ms=_grpc_ms(s["observed_at"]))
                    for s in body.get("samples", [])
                ],
            )
            list(stub.StreamMetrics(iter([batch]), metadata=md, timeout=15))
            return 200, {}
        if path == "/logs":
            batch = pb.LogBatch(
                node_id=NODE_ID,
                lines=[
                    pb.LogLine(
                        level=line["level"],
                        message=line["message"],
                        observed_at_unix_ms=_grpc_ms(line["observed_at"]),
                    )
                    for line in body.get("lines", [])
                ],
            )
            list(stub.StreamLogs(iter([batch]), metadata=md, timeout=15))
            return 200, {}
        if path == "/connections":
            batch = pb.ConnectionBatch(
                node_id=NODE_ID,
                samples=[pb.ConnectionSample(assignment_id=s["assignment_id"], source_ip=s["source_ip"]) for s in body.get("samples", [])],
            )
            stub.ReportConnections(batch, metadata=md, timeout=15)
            return 200, {}
        if path == "/provider-health":
            batch = pb.ProviderHealthBatch(
                node_id=NODE_ID,
                checks=[
                    pb.ProviderHealth(provider_name=c["provider_name"], status=c["status"], latency_ms=float(c.get("latency_ms") or 0), detail=c.get("detail") or "")
                    for c in body.get("checks", [])
                ],
            )
            stub.ReportProviderHealth(batch, metadata=md, timeout=15)
            return 200, {}
        if path == "/state":
            resp = stub.ReportState(
                pb.ReportedState(
                    node_id=NODE_ID,
                    config_version=body.get("config_version") or "",
                    agent_version=body.get("agent_version") or "",
                    applied_json=json.dumps(body.get("applied", {})),
                    provider_status=body.get("provider_status", {}),
                ),
                metadata=md,
                timeout=15,
            )
            return 200, {"remediated": resp.remediated}
        return None
    except Exception as exc:
        _log(f"grpc call {path} failed, falling back to HTTP: {exc}")
        with contextlib.suppress(Exception):
            if _grpc_channel is not None:
                _grpc_channel.close()
        _grpc_channel = None
        _grpc_stub = None
        return None


def _call(method: str, path: str, body: dict | None = None, known_version: str | None = None):
    if _grpc_ready():
        res = _grpc_call(path, body, known_version=known_version)
        if res is not None:
            return res
    return _http_call(method, path, body, known_version=known_version)


TLS_CERT_DIR = os.environ.get("XLINK_TLS_DIR", "/etc/ssl/xlink")


def _write_cert(sni: str, cert_pem: str, key_pem: str) -> tuple[str, str]:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in (sni or "default"))
    os.makedirs(TLS_CERT_DIR, exist_ok=True)
    cert_path = os.path.join(TLS_CERT_DIR, safe + ".cert.pem")
    key_path = os.path.join(TLS_CERT_DIR, safe + ".key.pem")
    for p, data in ((cert_path, cert_pem), (key_path, key_pem)):
        with open(p, "w") as f:
            f.write(data)
            f.flush()
            with contextlib.suppress(OSError):
                os.fsync(f.fileno())
    os.chmod(key_path, 0o600)
    return cert_path, key_path


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
        cert_pem = s.get("cert_pem")
        key_pem = s.get("key_pem")
        if cert_pem and key_pem:
            try:
                cert_path, key_path = _write_cert(s.get("sni") or "", cert_pem, key_pem)
                tls["certificates"] = [
                    {"certificateFile": cert_path, "keyFile": key_path}
                ]
            except OSError as exc:
                _log(f"tls_cert_write_failed sni={s.get('sni')} err={exc}")
        stream["tlsSettings"] = tls
    elif security == "reality":
        short = s.get("shortId") or s.get("short_id") or ""
        stream["realitySettings"] = {
            "show": False,
            "dest": s.get("dest") or ((s.get("sni") or "www.microsoft.com") + ":443"),
            "serverNames": [s["sni"]] if s.get("sni") else [],
            "privateKey": s.get("privateKey") or s.get("private_key") or "",
            "shortIds": [short] if short else [""],
        }
    return stream


def _default_ss_method(protocol: str) -> str:
    """Default cipher per shadowsocks family.

    A 2022 inbound given a pre-2022 cipher (or vice versa) is rejected by xray,
    which fails validation and freezes the node on its previous config.
    """
    if protocol == "shadowsocks2022":
        return "2022-blake3-aes-256-gcm"
    return "aes-256-gcm"


# Identity and the listen socket: forbidden at the TOP level only (`type` is a
# legitimate nested key, e.g. a sing-box transport's {"type": "ws"}).
_RAW_PROTECTED = frozenset({"tag", "listen", "port", "listen_port", "type", "protocol"})
# Credentials: forbidden at ANY depth. Xray keeps its user list at
# settings.clients, so a top-level-only filter let an override inject a client
# the panel never sees — no quota, no expiry, untouched by revocation.
_RAW_CREDENTIAL_KEYS = frozenset({"clients", "users", "accounts", "password", "uuid"})


def _strip_credentials(value, path=""):
    """Return `value` with credential keys removed at every depth, plus the
    dotted paths that were dropped."""
    dropped: list[str] = []
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            here = f"{path}.{k}" if path else k
            if k in _RAW_CREDENTIAL_KEYS:
                dropped.append(here)
                continue
            out[k], sub_dropped = _strip_credentials(v, here)
            dropped += sub_dropped
        return out, dropped
    if isinstance(value, list):
        out_list = []
        for i, item in enumerate(value):
            cleaned, sub_dropped = _strip_credentials(item, f"{path}[{i}]")
            out_list.append(cleaned)
            dropped += sub_dropped
        return out_list, dropped
    return value, dropped


def _deep_merge(base: dict, extra: dict) -> dict:
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _apply_raw_inbound(ib: dict, s: dict) -> dict:
    """Deep-merge an operator-supplied `rawInbound` onto a generated inbound.

    This is the escape hatch for core features the panel does not model yet:
    a new transport option, a sniffing tweak, a fallback, a mux setting. The
    operator writes the core's own JSON and it lands on the inbound unchanged,
    so a core upgrade no longer needs a panel release. Identity keys are
    rejected at the top level and credential keys (clients, users, accounts,
    password, uuid) at every depth, so the managed user list can be neither
    replaced nor extended.
    """
    raw = s.get("rawInbound")
    if not isinstance(raw, dict) or not raw:
        return ib
    top = {k: v for k, v in raw.items() if k not in _RAW_PROTECTED}
    safe, cred_dropped = _strip_credentials(top)
    dropped = sorted(set(raw) - set(top)) + cred_dropped
    if dropped:
        _log(f"rawInbound: ignored protected keys {dropped} on {ib.get('tag')}")
    return _deep_merge(ib, safe)


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
    if protocol in ("shadowsocks", "shadowsocks2022"):
        # xray has no "shadowsocks2022" protocol — 2022 is just a cipher family
        # on the shadowsocks inbound, selected via `method`.
        return {
            "password": cid,
            "email": email,
            "method": s.get("method", _default_ss_method(protocol)),
        }
    return {"id": cid, "email": email}


def _client_id(cl: dict) -> str:
    creds = cl.get("credentials") or {}
    s = cl.get("settings") or {}
    protocol = (cl.get("protocol") or "vless").lower()
    if protocol in (
        "trojan", "shadowsocks", "shadowsocks2022", "shadowtls",
        "hysteria2", "hysteria", "tuic", "naive", "socks",
    ):
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
        _stream_for_key = (
            {"network": "tcp", "security": "none"}
            if protocol == "socks"
            else _stream_settings(s)
        )
        key = (port, protocol, json.dumps(_stream_for_key, sort_keys=True))
        cid = _client_id(cl)
        email = cl.get("assignment_id")
        if key not in inbounds:
            if protocol == "socks":
                settings = {"auth": "password", "accounts": [], "udp": True}
            else:
                settings = {"clients": []}
                if protocol == "vless":
                    settings["decryption"] = "none"
                if protocol in ("shadowsocks", "shadowsocks2022"):
                    settings["method"] = s.get("method", _default_ss_method(protocol))
                if isinstance(s.get("fallbacks"), list) and protocol in ("vless", "trojan"):
                    settings["fallbacks"] = s["fallbacks"]
            network = (s.get("network") or "tcp").lower()
            stream = (
                {"network": "tcp", "security": "none"}
                if protocol == "socks"
                else _stream_settings(s)
            )
            # xray implements ss2022 as a cipher family on the shadowsocks
            # inbound; emitting "shadowsocks2022" as the protocol makes
            # `xray run -test` reject the file, and a rejected candidate leaves
            # the node pinned to its previous config for EVERY user on it.
            xray_protocol = "shadowsocks" if protocol == "shadowsocks2022" else protocol
            inbounds[key] = {
                "tag": f"in-{port}-{protocol}-{network}-{len(inbounds)}",
                "listen": "0.0.0.0",
                "port": port,
                "protocol": xray_protocol,
                "settings": settings,
                "streamSettings": stream,
                "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
            }
            _apply_raw_inbound(inbounds[key], s)
        if protocol == "socks":
            merged = {**s, **(cl.get("credentials") or {})}
            user = str(merged.get("username") or email or cid)
            inbounds[key]["settings"]["accounts"].append({"user": user, "pass": cid})
        else:
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
    log_block = dict(core.get("log") or {})
    log_block.setdefault("loglevel", "warning")
    log_block["error"] = XRAY_ERROR_LOG
    config: dict = {
        "log": log_block,
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
        pw = s.get("password") or cid
        return {"uuid": cid, "password": pw, "name": email}
    if protocol == "naive":
        return {
            "username": str(s.get("username") or email),
            "password": str(s.get("password") or cid),
            "name": str(email),
        }
    if protocol == "socks":
        user = str(s.get("username") or email or cid)
        return {"username": user, "password": str(s.get("password") or cid), "name": str(email)}
    if protocol == "shadowtls":
        return {"name": str(email), "password": cid}
    return {"password": cid, "name": email}


def _singbox_tls(s: dict) -> dict:
    security = (s.get("security") or "none").lower()
    if security == "reality":
        sni = s.get("sni") or "www.microsoft.com"
        short = s.get("shortId") or s.get("short_id") or ""
        dest = s.get("dest") or f"{sni}:443"
        host, _, port = dest.rpartition(":")
        return {
            "enabled": True,
            "server_name": sni,
            "reality": {
                "enabled": True,
                "handshake": {
                    "server": host or sni,
                    "server_port": int(port) if port.isdigit() else 443,
                },
                "private_key": s.get("privateKey") or s.get("private_key") or "",
                "short_id": [short] if short else [""],
            },
        }
    tls: dict = {"enabled": True}
    if s.get("sni"):
        tls["server_name"] = s["sni"]
    cert_pem, key_pem = s.get("cert_pem"), s.get("key_pem")
    if cert_pem and key_pem:
        try:
            cp, kp = _write_cert(s.get("sni") or s.get("host") or "default", cert_pem, key_pem)
            tls["certificate_path"], tls["key_path"] = cp, kp
        except OSError as exc:
            _log(f"tls_cert_write_failed sni={s.get('sni')} err={exc}")
    elif os.path.exists(TLS_CERT_PATH) and os.path.exists(TLS_KEY_PATH):
        tls["certificate_path"], tls["key_path"] = TLS_CERT_PATH, TLS_KEY_PATH
    return tls


def _singbox_transport(s: dict) -> dict | None:
    """Client-visible transport settings for a sing-box inbound.

    These keys must agree byte-for-byte with what the subscription renderers
    hand the client, so the field names here mirror the panel's (`serviceName`,
    `host`) rather than guessing from `path`.
    """
    network = (s.get("network") or "tcp").lower()
    host = str(s.get("host") or "").strip()
    if network in ("ws", "httpupgrade"):
        t: dict = {"type": network, "path": s.get("path") or "/"}
        if host:
            # The client sends Host; a CDN-fronted inbound that ignores it
            # cannot match the request.
            if network == "ws":
                t["headers"] = {"Host": host}
            else:
                # sing-box httpupgrade takes host as a top-level field.
                t["host"] = host
        return t
    if network == "grpc":
        # `serviceName` is what the panel writes and every client renderer
        # emits; reading `path` here silently broke every gRPC profile.
        return {"type": "grpc", "service_name": s.get("serviceName") or s.get("path") or ""}
    return None


_SB_TRANSPORT_OK = {"vless", "vmess", "trojan"}
_SB_TLS_OK = {"vless", "vmess", "trojan", "hysteria2", "tuic", "anytls"}
_SB_TLS_MANDATORY = {"hysteria2", "tuic", "anytls"}


def build_singbox_config(clients: list[dict]) -> dict:
    inbounds: dict[tuple, dict] = {}
    detours: dict[str, dict] = {}
    for cl in clients:
        protocol = cl.get("protocol", "vless")
        s = cl.get("settings") or {}
        port = int(s.get("port", 443) or 443)
        sec_mode = (s.get("security") or "none").lower()
        secure = sec_mode in ("tls", "reality")
        key = (
            port, protocol, sec_mode,
            str(s.get("sni") or s.get("serverName") or ""),
            str(s.get("method", "")),
            json.dumps(_singbox_transport(s) or {}, sort_keys=True),
        )
        cid = _client_id(cl)
        if key not in inbounds:
            ib: dict = {
                "type": protocol,
                "tag": f"in-{port}-{protocol}-{len(inbounds)}",
                "listen": "0.0.0.0",
                "listen_port": port,
                "users": [],
            }
            if protocol in ("shadowsocks", "shadowsocks2022"):
                ib["type"] = "shadowsocks"
                default_method = (
                    "2022-blake3-aes-256-gcm" if protocol == "shadowsocks2022" else "aes-256-gcm"
                )
                ib["method"] = s.get("method", default_method)
            elif protocol == "shadowtls":
                sni = s.get("sni") or s.get("handshake") or "www.microsoft.com"
                ss_tag = f"sstls-ss-{port}-{len(inbounds)}"
                detour_port = 40000 + len(detours)
                ib["version"] = 3
                ib["handshake"] = {"server": sni, "server_port": 443}
                ib["detour"] = ss_tag
                detours[ss_tag] = {
                    "type": "shadowsocks",
                    "tag": ss_tag,
                    "listen": "127.0.0.1",
                    "listen_port": detour_port,
                    "method": s.get("method", "aes-128-gcm"),
                    "users": [],
                    "_key": key,
                }
            elif protocol == "naive":
                ib["tls"] = _singbox_tls(s)
            else:
                tls_required = protocol in _SB_TLS_MANDATORY
                if (secure or tls_required) and protocol in _SB_TLS_OK:
                    ib["tls"] = _singbox_tls(s)
                transport = _singbox_transport(s)
                if transport and protocol in _SB_TRANSPORT_OK:
                    ib["transport"] = transport
            inbounds[key] = _apply_raw_inbound(ib, s)
        email = cl.get("assignment_id")
        user_view = {**s, **(cl.get("credentials") or {})}
        inbounds[key]["users"].append(_singbox_user(protocol, cid, email, user_view))
        if protocol == "shadowtls":
            for d in detours.values():
                if d.get("_key") == key:
                    d["users"].append({"name": str(email), "password": cid})
                    break
    core = _singbox_core if isinstance(_singbox_core, dict) else {}
    for d in detours.values():
        d.pop("_key", None)
    all_inbounds = list(inbounds.values()) + list(detours.values())
    user_names = sorted(
        {
            u["name"]
            for ib in all_inbounds
            for u in ib.get("users", [])
            if isinstance(u, dict) and u.get("name")
        }
    )
    experimental: dict = dict(core.get("experimental") or {})
    if _v2ray_enabled():
        experimental["v2ray_api"] = {
            "listen": SINGBOX_V2RAY_API_ADDR,
            "stats": {"enabled": True, "users": user_names},
        }
    else:
        experimental.setdefault("clash_api", {"external_controller": SINGBOX_API_ADDR})
    config: dict = {
        "log": core.get("log", {"level": "warn"}),
        "inbounds": all_inbounds,
        "outbounds": core.get("outbounds", [{"type": "direct"}]),
        "experimental": experimental,
    }
    for key_name in ("dns", "route", "ntp"):
        if core.get(key_name):
            config[key_name] = core[key_name]
    return config


def _wg_subnet(addr: str) -> str:
    import ipaddress
    try:
        a = addr.strip()
        if "/" not in a:
            a = a + "/24"
        net = ipaddress.ip_network(a, strict=False)
        if net.version != 4:
            return "10.8.0.0/24"
        return str(net)
    except (ValueError, TypeError):
        return "10.8.0.0/24"


_WG_KEY_RE = re.compile(r"^[A-Za-z0-9+/]{42,44}=?$")


def _wg_safe_key(value: str) -> str:
    v = (value or "").strip()
    if not _WG_KEY_RE.match(v):
        raise ValueError(f"invalid wireguard key: {v[:16]!r}")
    return v


def _wg_safe_addr(value: str) -> str:
    v = (value or "").strip()
    if not re.match(r"^[0-9a-fA-F:.]+(/[0-9]{1,3})?$", v):
        raise ValueError(f"invalid wireguard address: {v[:32]!r}")
    return v


def build_wireguard_config(clients: list[dict]) -> str:
    s0 = (clients[0].get("settings") or {}) if clients else {}
    port = int(s0.get("port", 51820) or 51820)
    if not (1 <= port <= 65535):
        port = 51820
    priv = _wg_safe_key(str(s0.get("privateKey") or s0.get("private_key") or WG_PRIVATE_KEY or ""))
    if not priv:
        raise RuntimeError("wireguard: no private key in settings or XLINK_WG_PRIVATE_KEY")
    addr = _wg_safe_addr(str(s0.get("address") or "10.8.0.1/24"))
    subnet = _wg_subnet(addr)
    psk = str(s0.get("presharedKey") or s0.get("preshared_key") or "").strip()
    try:
        psk = _wg_safe_key(psk) if psk else ""
    except ValueError:
        psk = ""
    wan_detect = (
        "WAN=$(ip -o route get 1.1.1.1 2>/dev/null | "
        "awk '{for(i=1;i<=NF;i++) if($i==\"dev\"){print $(i+1);exit}}'); "
        "[ -z \"$WAN\" ] && WAN=$(ip route list default 2>/dev/null | "
        "awk '{for(i=1;i<=NF;i++) if($i==\"dev\"){print $(i+1);exit}}'); "
    )
    post_up = (
        f"{wan_detect}"
        "sysctl -w net.ipv4.ip_forward=1; "
        "sysctl -w net.ipv4.conf.all.rp_filter=0; "
        "sysctl -w net.ipv4.conf.default.rp_filter=0; "
        "sysctl -w net.ipv4.conf.%i.rp_filter=0; "
        "[ -n \"$WAN\" ] && sysctl -w net.ipv4.conf.$WAN.rp_filter=0 2>/dev/null; "
        f"iptables -C INPUT -p udp --dport {port} -j ACCEPT 2>/dev/null || "
        f"iptables -I INPUT 1 -p udp --dport {port} -j ACCEPT 2>/dev/null; "
        "[ -z \"$WAN\" ] && { echo 'wireguard: no WAN interface detected, skipping NAT'; exit 0; }; "
        f"if iptables -t nat -A POSTROUTING -s {subnet} -o \"$WAN\" -j MASQUERADE 2>/dev/null; then "
        "iptables -I FORWARD 1 -i %i -j ACCEPT; "
        "iptables -I FORWARD 1 -o %i -j ACCEPT; "
        "if iptables -L DOCKER-USER >/dev/null 2>&1; then "
        "iptables -I DOCKER-USER 1 -i %i -j ACCEPT; "
        "iptables -I DOCKER-USER 1 -o %i -j ACCEPT; fi; "
        "else "
        "nft add table ip wgnat 2>/dev/null; "
        "nft 'add chain ip wgnat post { type nat hook postrouting priority 100 ; }' 2>/dev/null; "
        f"nft add rule ip wgnat post ip saddr {subnet} oifname \"$WAN\" masquerade; "
        "nft 'add chain ip wgnat wgfwd { type filter hook forward priority 0 ; }' 2>/dev/null; "
        "nft add rule ip wgnat wgfwd iifname %i accept; "
        "nft add rule ip wgnat wgfwd oifname %i accept; "
        "fi"
    )
    post_down = (
        f"{wan_detect}"
        f"iptables -D INPUT -p udp --dport {port} -j ACCEPT 2>/dev/null; "
        f"[ -n \"$WAN\" ] && iptables -t nat -D POSTROUTING -s {subnet} -o \"$WAN\" -j MASQUERADE 2>/dev/null; "
        "iptables -D FORWARD -i %i -j ACCEPT 2>/dev/null; "
        "iptables -D FORWARD -o %i -j ACCEPT 2>/dev/null; "
        "iptables -D DOCKER-USER -i %i -j ACCEPT 2>/dev/null; "
        "iptables -D DOCKER-USER -o %i -j ACCEPT 2>/dev/null; "
        "nft delete table ip wgnat 2>/dev/null; "
        "true"
    )
    lines = [
        "[Interface]",
        f"ListenPort = {port}",
        f"PrivateKey = {priv}",
        f"Address = {addr}",
    ]
    mtu = s0.get("mtu")
    try:
        mtu_val = int(mtu) if mtu not in (None, "") else 0
    except (TypeError, ValueError):
        mtu_val = 0
    # Clamp rather than omit: silently dropping the line left the server on the
    # 1420 kernel default while the client config carried the operator's value.
    # Unset pins the same 1420 default the client renderer emits.
    mtu_val = max(1280, min(1500, mtu_val)) if mtu_val else 1420
    lines.append(f"MTU = {mtu_val}")
    lines += [
        f"PostUp = {post_up}",
        f"PostDown = {post_down}",
    ]
    server_ip = addr.split("/")[0].strip()
    server_priv = str(s0.get("privateKey") or s0.get("private_key") or "").strip()
    seen_ips: set[str] = set()
    skipped_foreign = 0
    skipped_no_addr = 0
    for cl in clients:
        cs = cl.get("settings") or {}
        cl_priv = str(cs.get("privateKey") or cs.get("private_key") or "").strip()
        if server_priv and cl_priv and cl_priv != server_priv:
            skipped_foreign += 1
            continue
        creds = cl.get("credentials") or {}
        try:
            pub = _wg_safe_key(str(creds.get("public_key") or ""))
        except ValueError:
            continue
        if not pub:
            continue
        peer_addr = str(creds.get("address") or "").strip()
        ip = peer_addr.split("/")[0].strip()
        if not ip:
            skipped_no_addr += 1
            continue
        if ip == server_ip or ip in seen_ips:
            continue
        try:
            _wg_safe_addr(ip)
        except ValueError:
            continue
        seen_ips.add(ip)
        peer_lines = ["", "[Peer]", f"PublicKey = {pub}"]
        peer_psk = str(creds.get("preshared_key") or creds.get("presharedKey") or "").strip()
        try:
            peer_psk = _wg_safe_key(peer_psk) if peer_psk else ""
        except ValueError:
            peer_psk = ""
        effective_psk = peer_psk or psk
        if effective_psk:
            peer_lines.append(f"PresharedKey = {effective_psk}")
        peer_lines.append(f"AllowedIPs = {ip}/32")
        lines += peer_lines
    if skipped_foreign:
        _log(
            f"wireguard: {skipped_foreign} client(s) belong to a different WG server "
            "profile on this node and were skipped (one wg0 interface per node)"
        )
    if skipped_no_addr:
        _log(f"wireguard: {skipped_no_addr} client(s) skipped — no tunnel address in credentials")
    return "\n".join(lines) + "\n"


def build_hysteria_config(clients: list[dict]) -> dict:
    s0 = (clients[0].get("settings") or {}) if clients else {}
    port = int(s0.get("port", 443) or 443)
    other_ports = {int((c.get("settings") or {}).get("port", 443) or 443) for c in clients}
    if len(other_ports) > 1:
        _log(f"hysteria: multiple ports {sorted(other_ports)} collapse onto :{port} "
             "(single-instance daemon) — clients on the other ports will not connect")
    core = _hysteria_core if isinstance(_hysteria_core, dict) else {}
    userpass = {}
    for c in clients:
        cid = _client_id(c)
        aid = c.get("assignment_id")
        if aid:
            userpass[str(aid)] = cid
    config = {
        "listen": f":{port}",
        "tls": {"cert": TLS_CERT_PATH, "key": TLS_KEY_PATH},
        "auth": {"type": "userpass", "userpass": userpass},
        "trafficStats": {"listen": HYSTERIA_API_ADDR, "secret": HYSTERIA_API_SECRET},
    }
    for c in clients:
        cs = {**(c.get("settings") or {}), **(c.get("credentials") or {})}
        obfs_pw = cs.get("obfsPassword") or cs.get("obfs_password")
        if cs.get("obfs") and obfs_pw:
            config["obfs"] = {"type": "salamander", "salamander": {"password": str(obfs_pw)}}
            break
    for key_name in ("acl", "outbounds", "bandwidth", "masquerade", "log", "resolver", "sniff"):
        if core.get(key_name):
            config[key_name] = core[key_name]
    return config


WG_INTERFACE = os.environ.get("XLINK_WG_INTERFACE", "wg0")
WG_CONFIG_PATH = os.environ.get("XLINK_WG_CONFIG", f"/etc/wireguard/{WG_INTERFACE}.conf")

_WG_RELOAD_DEFAULT = (
    f"if ip link show {WG_INTERFACE} >/dev/null 2>&1; then "
    f"wg syncconf {WG_INTERFACE} <(wg-quick strip {WG_INTERFACE}) || "
    f"{{ (wg-quick down {WG_INTERFACE} 2>/dev/null; ip link delete {WG_INTERFACE} 2>/dev/null); "
    f"wg-quick up {WG_INTERFACE}; }}; "
    f"else wg-quick up {WG_INTERFACE}; fi; "
    "WAN=$(ip route list default | awk '{print $5; exit}'); "
    "sysctl -w net.ipv4.ip_forward=1 >/dev/null; "
    "sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null; "
    "sysctl -w net.ipv4.conf.default.rp_filter=0 >/dev/null; "
    f"sysctl -w net.ipv4.conf.{WG_INTERFACE}.rp_filter=0 >/dev/null 2>&1; "
    "sysctl -w net.ipv4.conf.$WAN.rp_filter=0 >/dev/null 2>&1; "
    "WG_SUBNET=$(awk -F'[=,/ ]+' '/^Address/{print $2\"/\"$3; exit}' "
    f"{WG_CONFIG_PATH} 2>/dev/null | "
    "python3 -c 'import sys,ipaddress; "
    "a=sys.stdin.read().strip() or \"10.8.0.1/24\"; "
    "a=a if \"/\" in a else a+\"/24\"; "
    "print(ipaddress.ip_network(a,strict=False))' 2>/dev/null); "
    "[ -z \"$WG_SUBNET\" ] && WG_SUBNET=10.8.0.0/24; "
    "iptables -t nat -C POSTROUTING -s $WG_SUBNET -o $WAN -j MASQUERADE 2>/dev/null || "
    "iptables -t nat -A POSTROUTING -s $WG_SUBNET -o $WAN -j MASQUERADE; "
    f"iptables -C FORWARD -i {WG_INTERFACE} -j ACCEPT 2>/dev/null || "
    f"iptables -I FORWARD 1 -i {WG_INTERFACE} -j ACCEPT; "
    f"iptables -C FORWARD -o {WG_INTERFACE} -j ACCEPT 2>/dev/null || "
    f"iptables -I FORWARD 1 -o {WG_INTERFACE} -j ACCEPT; "
    "if iptables -L DOCKER-USER >/dev/null 2>&1; then "
    f"iptables -C DOCKER-USER -i {WG_INTERFACE} -j ACCEPT 2>/dev/null || "
    f"iptables -I DOCKER-USER 1 -i {WG_INTERFACE} -j ACCEPT; "
    f"iptables -C DOCKER-USER -o {WG_INTERFACE} -j ACCEPT 2>/dev/null || "
    f"iptables -I DOCKER-USER 1 -o {WG_INTERFACE} -j ACCEPT; "
    "fi"
)


CORE_PROTOCOLS: dict[str, frozenset[str]] = {
    "xray": frozenset({"vless", "vmess", "trojan", "shadowsocks", "shadowsocks2022"}),
    "sing-box": frozenset(
        {
            "vless",
            "vmess",
            "trojan",
            "shadowsocks",
            "shadowsocks2022",
            "shadowtls",
            "hysteria2",
            "tuic",
            "anytls",
            "naive",
            "socks",
        }
    ),
    "hysteria": frozenset({"hysteria2"}),
    "wireguard": frozenset({"wireguard"}),
}


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
        "path": WG_CONFIG_PATH,
        "reload": os.environ.get("XLINK_WG_RELOAD", _WG_RELOAD_DEFAULT),
        "validate": None,
        "service": os.environ.get("XLINK_WG_SERVICE", f"wg-quick@{WG_INTERFACE}"),
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


def check_provider_health(
    health_kinds: set[str], serving_kinds: set[str] | None = None
) -> dict[str, str]:
    serving = serving_kinds if serving_kinds is not None else health_kinds
    status: dict[str, str] = {}
    for kind in health_kinds:
        core = CORES.get(kind)
        if core is None:
            continue
        try:
            if not _core_installed(kind, core):
                status[kind] = "not_installed"
                continue
            if kind == "xray":
                healthy = _xray_api_ok()
                if not healthy:
                    active = _systemd_active(core.get("service", "xray"))
                    if active:
                        healthy = True
            elif kind == "wireguard":
                rc, _ = _run(f"ip link show {WG_INTERFACE}")
                healthy = rc == 0
            else:
                active = _systemd_active(core.get("service", ""))
                healthy = os.path.exists(core["path"]) if active is None else active
            if not healthy and kind not in serving:
                status[kind] = "healthy"
                continue
            status[kind] = "healthy" if healthy else "unhealthy"
        except Exception as exc:
            _log(f"{kind}: health probe failed: {exc}")
            status[kind] = "unhealthy"
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
        if peer not in _wg_prev:
            _wg_prev[peer] = (rx_b, tx_b)
            continue
        prev_rx, prev_tx = _wg_prev[peer]
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
    for dead in set(_wg_prev) - set(peer_to_assignment):
        del _wg_prev[dead]
    return samples


def _write(path: str, built, fmt: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        if fmt == "json":
            json.dump(built, fh, indent=2)
        else:
            fh.write(built)
        fh.flush()
        with contextlib.suppress(OSError):
            os.fsync(fh.fileno())
    os.replace(tmp, path)


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
    if not core_clients:
        if not os.path.exists(path):
            return True
        if kind == "wireguard":
            _run(
                f"wg-quick down {WG_INTERFACE} 2>/dev/null; "
                f"ip link delete {WG_INTERFACE} 2>/dev/null"
            )
            with contextlib.suppress(OSError):
                os.remove(path)
            _log(f"{kind}: drained (no clients) — interface down")
            return True
        try:
            empty = core["builder"]([])
        except Exception as exc:
            _log(f"{kind}: drain build error: {exc}")
            return False
        _write(path, empty, core["fmt"])
        rc, out = _run(core["reload"])
        _log(f"{kind}: drained (no clients) — emptied config, reload rc={rc}")
        return rc == 0
    root, ext = os.path.splitext(path)
    tmp = f"{root}.tmp{ext}"
    backup = f"{root}.bak{ext}"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if kind == "xray":
        with contextlib.suppress(OSError):
            os.makedirs(os.path.dirname(XRAY_ERROR_LOG) or ".", exist_ok=True)
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


def apply_config(clients: list[dict], version: str, server_version: str | None = None) -> set[str]:
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
        if not core_clients:
            try:
                if apply_one(kind, core, []):
                    _core_hash.pop(kind, None)
                else:
                    ok = False
            except Exception as exc:  # noqa: BLE001
                ok = False
                _log(f"{kind} drain error: {exc}")
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
        _last_version = server_version if server_version is not None else version
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
    with _OPENER.open(req, timeout=timeout) as resp:
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
            stderr=subprocess.DEVNULL,
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
    clean = []
    for s in samples:
        try:
            uuid.UUID(str(s.get("assignment_id")))
        except (ValueError, AttributeError, TypeError):
            continue
        clean.append(s)
    return clean


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
        user_base[uid] = int(c.get("used_bytes", 0) or 0)
    for s in samples:
        uid = asg_user.get(s.get("assignment_id"))
        if uid is None:
            continue
        used = int(s.get("upload_bytes", 0) or 0) + int(s.get("download_bytes", 0) or 0)
        _usage_acc[uid] = _usage_acc.get(uid, 0) + used
    live_users = {c.get("user_id") for c in clients}
    for dead in [u for u in _usage_acc if u not in live_users]:
        del _usage_acc[dead]
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


_XLINK_CLI = os.environ.get("XLINK_CLI", "/usr/local/bin/xlink")
_UPGRADE_TIMEOUT = 900
_CORE_ALIAS = {"singbox": "sing-box", "wg": "wireguard"}


def _run_command(kind: str, payload: dict) -> tuple[bool, dict]:
    if kind == "apply_config":
        _wake.set()
        return True, {"note": "config refresh scheduled"}
    if kind == "restart":
        core = str(payload.get("core") or "").lower()
        core = _CORE_ALIAS.get(core, core)
        spec = CORES.get(core)
        if spec is None:
            return False, {"error": f"unknown core {core}"}
        if not _core_installed(core, spec):
            return True, {"core": core, "note": "core not installed — nothing to restart"}
        service = spec.get("service", core)
        rc, out = _run(f"systemctl restart {service}")
        return rc == 0, {"core": core, "rc": rc, "output": out[-500:] if out else ""}
    if kind == "upgrade":
        core = str(payload.get("core") or "").lower()
        core = _CORE_ALIAS.get(core, core)
        if core not in CORES:
            return False, {"error": f"unknown or missing core {core!r}"}
        alias = {"sing-box": "singbox", "wireguard": "wg"}.get(core, core)
        target = str(payload.get("target_version") or "").strip()
        if target and not re.match(r"^[A-Za-z0-9._-]+$", target):
            return False, {"error": f"invalid target_version: {target[:32]!r}"}
        if not os.path.exists(_XLINK_CLI):
            return False, {"error": "xlink CLI not found"}
        cmd = [_XLINK_CLI, "core-update", alias]
        if target:
            cmd.append(target)
        try:
            proc = subprocess.run(
                cmd,
                timeout=_UPGRADE_TIMEOUT,
                capture_output=True,
                text=True,
                errors="replace",
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, {"error": str(exc)}
        return proc.returncode == 0, {
            "core": core,
            "rc": proc.returncode,
            "output": (proc.stdout + proc.stderr)[-500:],
        }
    return False, {"error": f"unsupported command kind {kind}"}


_cmd_lock = threading.Lock()


def poll_commands() -> None:
    if _cmd_lock.locked():
        return
    threading.Thread(target=_poll_commands_blocking, daemon=True).start()


def _poll_commands_blocking() -> None:
    if not _cmd_lock.acquire(blocking=False):
        return
    try:
        _do_poll_commands()
    finally:
        _cmd_lock.release()


def _do_poll_commands() -> None:
    try:
        sc, resp = _call("POST", "/commands/lease", {})
    except Exception as exc:
        _log(f"command lease error: {exc}")
        return
    if sc != 200 or not isinstance(resp, dict):
        return
    lease_token = resp.get("lease_token")
    commands = resp.get("commands") or []
    if not lease_token or not commands:
        return
    for cmd in commands:
        cid = cmd.get("command_id")
        kind = cmd.get("kind")
        payload = cmd.get("payload") or {}
        if not cid or not kind:
            continue
        _log(f"executing command {kind} ({cid})")
        try:
            success, result = _run_command(kind, payload)
        except Exception as exc:
            success, result = False, {"error": str(exc)}
        delivered = False
        for _ in range(3):
            try:
                rsc, _ = _call(
                    "POST",
                    "/commands/result",
                    {
                        "command_id": cid,
                        "lease_token": lease_token,
                        "success": bool(success),
                        "result": result,
                    },
                )
                if rsc == 200:
                    delivered = True
                    break
            except Exception:
                pass
            time.sleep(2)
        if not delivered:
            _log(f"command {kind} ({cid}) result NOT delivered — may re-run")
        _log(f"command {kind} ({cid}) -> {'ok' if success else 'failed'}")


def cycle() -> None:
    global _xray_core, _singbox_core, _hysteria_core
    global _usage_acc, _over_users
    global _last_clients, _last_kinds, _last_effective_version
    sc, cfg = _call("GET", "/config", known_version=_last_version)
    if sc != 200:
        _log(f"config pull failed ({sc}): {cfg}")
        with contextlib.suppress(Exception):
            _call("POST", "/state", {"agent_version": AGENT_VERSION})
        return
    version = cfg.get("config_version")
    conf = cfg.get("config") or {}
    unchanged = bool(cfg.get("unchanged")) or (
        version is not None and version == _last_version and not conf.get("clients")
    )
    if unchanged and _last_clients:
        clients = _last_clients
        cores = None
        _log(f"config unchanged v={version} (short-circuit) clients={len(clients)}")
    else:
        clients = conf.get("clients", [])
        cores = conf.get("core_templates") or {}
        _log(f"pulled config v={version} clients={len(clients)}")

    kinds_present = {_effective_core(c) for c in clients} & set(CORES)
    pre_samples: list[dict] = []
    active_kinds: set[str] = set()
    locally_limited = 0
    try:
        with _enforce_lock:
            if cores is not None:
                _xray_core = cores.get("xray") or {}
                _singbox_core = cores.get("sing-box") or {}
                _hysteria_core = cores.get("hysteria") or {}
                _usage_acc = {}
                _over_users = set()
            pre_samples = collect_traffic(kinds_present, clients) if not DRY_RUN else []
            _wal_append(pre_samples)
            effective = _local_enforce(clients, pre_samples)
            locally_limited = len(clients) - len(effective)
            effective_version = (
                f"{version}-local{len(effective)}" if locally_limited else version
            )
            if cores is not None or locally_limited:
                active_kinds = apply_config(effective, effective_version, server_version=version)
            else:
                active_kinds = {_effective_core(c) for c in clients} & set(CORES)
            _last_clients = clients
            _last_kinds = kinds_present
            _last_effective_version = effective_version
    except Exception as exc:
        _log(f"apply cycle error (continuing to report state): {exc}")
        active_kinds = {_effective_core(c) for c in clients} & set(CORES)

    cpu, mem = read_metrics()
    def _installed_safe(k: str) -> bool:
        try:
            return _core_installed(k, CORES[k])
        except Exception:
            return False

    health_kinds = active_kinds | {k for k in CORES if _installed_safe(k)}
    provider_status = (
        check_provider_health(health_kinds, serving_kinds=active_kinds)
        if not DRY_RUN
        else {}
    )
    unhealthy = [k for k, v in provider_status.items() if v != "healthy"]
    if unhealthy:
        _log(f"provider health: UNHEALTHY {unhealthy} (status={provider_status})")
    _call(
        "POST",
        "/state",
        {
            "config_version": version,
            "agent_version": AGENT_VERSION,
            "applied": {"config_version": version, "locally_limited": locally_limited},
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

    samples = _wal_rotate()
    if samples:
        digest = hashlib.sha256(
            json.dumps(samples, sort_keys=True).encode()
        ).hexdigest()[:32]
        batch = f"{NODE_ID}-{digest}"
        sc, _ = _call("POST", "/traffic", {"batch_id": batch, "samples": samples})
        if sc == 200:
            _wal_commit(len(samples))
            _log(f"reported traffic for {len(samples)} client(s) ({sc})")
        else:
            _log(f"traffic report failed ({sc}); {len(samples)} sample(s) held in WAL")

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
    out_lines = [
        {"level": _xray_level(ln), "message": ln, "observed_at": ts, "source": "xray"}
        for ln in read_core_logs()
    ]
    for kind in CORES:
        if kind == "xray" or not _installed_safe(kind):
            continue
        service = CORES[kind].get("service", "")
        if not service:
            continue
        out_lines += [
            {"level": _journal_level(ln), "message": ln, "observed_at": ts, "source": kind}
            for ln in read_service_logs(service)
        ]
    if out_lines:
        _call("POST", "/logs", {"lines": out_lines[:1000]})


# A healthy event stream stays open for minutes; one that ends faster than this
# is treated as a failure for backoff purposes, however cleanly it closed.
_SSE_HEALTHY_SECONDS = 30.0
_SSE_BACKOFF_MAX = 60.0


def sse_listener() -> None:
    url = f"{BASE}/events"
    _sse_fail = 0
    while True:
        started = time.monotonic()
        try:
            req = urllib.request.Request(
                url, headers={"X-Agent-Token": TOKEN, "Accept": "text/event-stream"}
            )
            with _OPENER.open(req, timeout=90) as resp:
                for raw in resp:
                    if raw.decode("utf-8", "ignore").startswith("data:"):
                        _wake.set()
            reason = "stream closed"
        except Exception as exc:  # noqa: BLE001
            reason = str(exc)
        # Back off on EVERY disconnect, not only on exceptions. A server or proxy
        # that ends the stream cleanly (panel restart, idle timeout, an endpoint
        # answering with an empty body) used to drop straight back into the loop
        # with no sleep at all: ~2,900 reconnects per second per node, which
        # with a fleet of nodes is a self-inflicted DoS on the panel.
        if time.monotonic() - started >= _SSE_HEALTHY_SECONDS:
            _sse_fail = 0
        _sse_fail += 1
        if _sse_fail == 1 or _sse_fail % 12 == 0:
            _log(f"event stream reconnecting ({reason})")
        delay = min(_SSE_BACKOFF_MAX, 2.0 * (2 ** min(_sse_fail - 1, 5)))
        time.sleep(delay * (0.5 + random.random() / 2))  # jitter: no fleet-wide thundering herd


def fast_enforce_loop() -> None:
    if DRY_RUN:
        return
    while True:
        time.sleep(FAST_INTERVAL)
        if not _last_clients:
            continue
        try:
            with _enforce_lock:
                clients = _last_clients
                kinds = _last_kinds
                base_version = _last_effective_version
                clean_version = _last_version
                if not clients or not kinds:
                    continue
                prev_over = set(_over_users)
                samples = collect_traffic(kinds, clients)
                _wal_append(samples)
                effective = _local_enforce(clients, samples)
                newly_over = _over_users - prev_over
                if newly_over:
                    apply_config(
                        effective,
                        f"{base_version}-fast{len(effective)}",
                        server_version=clean_version,
                    )
                    _log(f"fast-enforce dropped {len(newly_over)} over-limit user(s)")
        except Exception as exc:
            _log(f"fast-enforce error: {exc}")


def main() -> int:
    if not NODE_ID or not TOKEN:
        print("Set XLINK_NODE_ID and XLINK_AGENT_TOKEN.", file=sys.stderr)
        return 2
    _log(f"xlink-agent → {PANEL_URL} node={NODE_ID} every {INTERVAL}s dry_run={DRY_RUN}")
    if not DRY_RUN:
        with contextlib.suppress(OSError):
            os.makedirs(os.path.dirname(XRAY_ERROR_LOG) or ".", exist_ok=True)
    workers = {
        "sse": (sse_listener, None),
        "fast-enforce": (fast_enforce_loop, None),
    }

    def _spawn(target):
        th = threading.Thread(target=target, daemon=True)
        th.start()
        return th

    threads = {name: _spawn(fn) for name, (fn, _) in workers.items()}
    while True:
        try:
            cycle()
        except Exception as exc:
            _log(f"cycle error: {exc}")
        try:
            poll_commands()
        except Exception as exc:
            _log(f"command poll error: {exc}")
        for name, (fn, _) in workers.items():
            if not threads[name].is_alive():
                _log(f"worker '{name}' died — respawning")
                threads[name] = _spawn(fn)
        jitter = INTERVAL * (1 + random.uniform(-0.2, 0.2))
        _wake.wait(timeout=max(1.0, jitter))
        _wake.clear()


if __name__ == "__main__":
    raise SystemExit(main())
