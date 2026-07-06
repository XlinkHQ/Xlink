from __future__ import annotations

import base64
import binascii
import json
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


def _b64(s: str) -> str:
    s = s.strip()
    pad = len(s) % 4
    if pad:
        s += "=" * (4 - pad)
    try:
        return base64.urlsafe_b64decode(s).decode("utf-8", "replace")
    except (binascii.Error, ValueError):
        return ""


def _host_port(netloc: str) -> tuple[str, str]:
    host = netloc
    port = ""
    if netloc.startswith("["):
        end = netloc.find("]")
        host = netloc[: end + 1]
        rest = netloc[end + 1 :]
        if rest.startswith(":"):
            port = rest[1:]
    elif ":" in netloc:
        host, port = netloc.rsplit(":", 1)
    return host, port


def _stream_from_qs(qs: dict[str, list[str]]) -> dict[str, Any]:
    g = lambda k: qs.get(k, [""])[0]  # noqa: E731
    out: dict[str, Any] = {}
    net = g("type") or "tcp"
    if net and net != "tcp":
        out["network"] = net
    sec = g("security")
    if sec in ("tls", "reality"):
        out["security"] = sec
        if g("sni"):
            out["sni"] = g("sni")
        if g("fp"):
            out["fingerprint"] = g("fp")
        if sec == "reality":
            if g("pbk"):
                out["publicKey"] = g("pbk")
            if g("sid"):
                out["shortId"] = g("sid")
    if net in ("ws", "httpupgrade"):
        if g("path"):
            out["path"] = unquote(g("path"))
        if g("host"):
            out["host"] = g("host")
    if net == "grpc" and g("serviceName"):
        out["serviceName"] = g("serviceName")
    if g("flow"):
        out["flow"] = g("flow")
    return out


def _parse_vless_trojan(link: str, proto: str) -> tuple[str, dict[str, Any]] | None:
    u = urlparse(link)
    host, port = _host_port(u.netloc.split("@")[-1])
    cred = unquote(u.username or "")
    if not host or not port or not cred:
        return None
    qs = parse_qs(u.query)
    settings: dict[str, Any] = {"address": f"{host}:{port}", **_stream_from_qs(qs)}
    if proto == "vless":
        settings["id"] = cred
        settings["encryption"] = "none"
    else:
        settings["password"] = cred
    return proto, settings


def _parse_vmess(link: str) -> tuple[str, dict[str, Any]] | None:
    raw = _b64(link[len("vmess://"):])
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return None
    host = str(d.get("add", ""))
    port = str(d.get("port", ""))
    uid = str(d.get("id", ""))
    if not host or not port or not uid:
        return None
    settings: dict[str, Any] = {"address": f"{host}:{port}", "id": uid}
    net = str(d.get("net", "tcp"))
    if net != "tcp":
        settings["network"] = net
    if d.get("tls") in ("tls", "reality"):
        settings["security"] = d["tls"]
        if d.get("sni"):
            settings["sni"] = d["sni"]
    if net in ("ws", "httpupgrade"):
        if d.get("path"):
            settings["path"] = d["path"]
        if d.get("host"):
            settings["host"] = d["host"]
    return "vmess", settings


def _parse_ss(link: str) -> tuple[str, dict[str, Any]] | None:
    body = link[len("ss://"):]
    body = body.split("#", 1)[0]
    if "@" in body:
        creds, server = body.rsplit("@", 1)
        method_pw = _b64(creds) if ":" not in creds else creds
    else:
        decoded = _b64(body)
        if "@" not in decoded:
            return None
        method_pw, server = decoded.rsplit("@", 1)
    if ":" not in method_pw:
        return None
    method, password = method_pw.split(":", 1)
    host, port = _host_port(server)
    if not host or not port:
        return None
    return "shadowsocks", {
        "address": f"{host}:{port}",
        "method": method,
        "password": password,
    }


def _outbound_from_xray(node: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    proto = str(node.get("protocol", "")).lower()
    s = node.get("settings") or {}
    ss = node.get("streamSettings") or {}
    stream: dict[str, Any] = {}
    net = ss.get("network")
    if net and net != "tcp":
        stream["network"] = net
    sec = ss.get("security")
    if sec in ("tls", "reality"):
        stream["security"] = sec
        tls = ss.get("tlsSettings") or ss.get("realitySettings") or {}
        if tls.get("serverName"):
            stream["sni"] = tls["serverName"]
        if tls.get("fingerprint"):
            stream["fingerprint"] = tls["fingerprint"]
        if tls.get("publicKey"):
            stream["publicKey"] = tls["publicKey"]
        if tls.get("shortId"):
            stream["shortId"] = tls["shortId"]
    ws = ss.get("wsSettings") or ss.get("httpupgradeSettings") or {}
    if ws.get("path"):
        stream["path"] = ws["path"]
    if ws.get("host"):
        stream["host"] = ws["host"]

    if proto in ("vless", "vmess"):
        vnext = (s.get("vnext") or [{}])[0]
        user = (vnext.get("users") or [{}])[0]
        host, port = str(vnext.get("address", "")), str(vnext.get("port", ""))
        if not host or not port or not user.get("id"):
            return None
        st = {"address": f"{host}:{port}", "id": user["id"], **stream}
        if proto == "vless":
            st["encryption"] = "none"
            if user.get("flow"):
                st["flow"] = user["flow"]
        return proto, st
    if proto in ("trojan", "shadowsocks", "socks", "http"):
        srv = (s.get("servers") or [{}])[0]
        host, port = str(srv.get("address", "")), str(srv.get("port", ""))
        if not host or not port:
            return None
        st = {"address": f"{host}:{port}", **stream}
        if proto == "trojan":
            st["password"] = srv.get("password", "")
        elif proto == "shadowsocks":
            st["method"] = srv.get("method", "")
            st["password"] = srv.get("password", "")
        return proto, st
    return None


def parse_import(text: str) -> dict[str, Any] | None:
    """Detect and parse a share link or an Xray/V2Box config JSON into
    {type, settings} for an outbound. Returns None if nothing usable."""
    text = text.strip()
    if not text:
        return None
    lower = text.lower()
    result: tuple[str, dict[str, Any]] | None = None
    if lower.startswith("vless://"):
        result = _parse_vless_trojan(text, "vless")
    elif lower.startswith("trojan://"):
        result = _parse_vless_trojan(text, "trojan")
    elif lower.startswith("vmess://"):
        result = _parse_vmess(text)
    elif lower.startswith("ss://"):
        result = _parse_ss(text)
    elif text.startswith("{"):
        try:
            doc = json.loads(text)
        except json.JSONDecodeError:
            return None
        outs = doc.get("outbounds") if isinstance(doc, dict) else None
        if isinstance(outs, list):
            builtin = {"freedom", "blackhole", "dns", "loopback"}
            for node in outs:
                if not isinstance(node, dict):
                    continue
                if str(node.get("protocol", "")).lower() in builtin:
                    continue
                result = _outbound_from_xray(node)
                if result:
                    break
        elif isinstance(doc, dict) and doc.get("protocol"):
            result = _outbound_from_xray(doc)
    if result is None:
        return None
    return {"type": result[0], "settings": result[1]}
