"""Score candidate REALITY targets ("dest"/serverNames).

A good target speaks TLS 1.3, negotiates h2, offers X25519, presents a
certificate valid for the SNI and answers quickly. Probes connect to the
resolved IP (pinned, so DNS rebinding cannot redirect the second handshake)
and refuse non-public addresses: the panel host must not become a scanner
for its own private network.

The scan runs from the panel. A target that is fast from the panel can be
slow or blocked from a node's region, so treat ``latency_ms`` as relative.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import socket
import ssl
import time
from dataclasses import asdict, dataclass, field

from app.webhooks.dispatcher import _is_blocked_ip

MAX_TARGETS = 20
_TIMEOUT_S = 5.0
_CONCURRENCY = 5


@dataclass
class ScanResult:
    target: str
    port: int
    ip: str | None = None
    ok: bool = False
    tls13: bool = False
    h2: bool = False
    x25519: bool | None = None
    cert_valid: bool = False
    latency_ms: float | None = None
    issuer: str | None = None
    problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def parse_target(raw: str) -> tuple[str, int]:
    raw = raw.strip().lower()
    for prefix in ("https://", "http://"):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
    raw = raw.split("/", 1)[0]
    host, port = raw, 443
    if raw.count(":") == 1:
        host, p = raw.rsplit(":", 1)
        if not p.isdigit() or not 0 < int(p) < 65536:
            raise ValueError(f"Bad port in {raw!r}.")
        port = int(p)
    if not host or len(host) > 253:
        raise ValueError(f"Bad host {raw!r}.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host, port
    raise ValueError("REALITY needs a domain name (SNI), not an IP.")


async def _handshake(
    ip: str, port: int, sni: str, *, verify: bool, curve: str | None = None
) -> tuple[dict, float]:
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.set_alpn_protocols(["h2", "http/1.1"])
    if curve:
        ctx.set_ecdh_curve(curve)
    started = time.perf_counter()
    _reader, writer = await asyncio.wait_for(
        asyncio.open_connection(ip, port, ssl=ctx, server_hostname=sni), _TIMEOUT_S
    )
    elapsed = (time.perf_counter() - started) * 1000
    obj = writer.get_extra_info("ssl_object")
    # Read everything now: the SSL object is unusable once the stream closes.
    facts: dict = {}
    if obj is not None:
        cert = obj.getpeercert() or {}
        issuer = dict(x[0] for x in cert.get("issuer", ()) if x)
        facts = {
            "version": obj.version(),
            "alpn": obj.selected_alpn_protocol(),
            "issuer": issuer.get("organizationName") or issuer.get("commonName"),
        }
    writer.close()
    with contextlib.suppress(TimeoutError, OSError, ssl.SSLError):
        await asyncio.wait_for(writer.wait_closed(), 1.0)
    return facts, elapsed


async def scan_one(raw: str) -> ScanResult:
    try:
        host, port = parse_target(raw)
    except ValueError as exc:
        return ScanResult(target=raw, port=0, problems=[str(exc)])
    res = ScanResult(target=host, port=port)
    try:
        infos = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM),
            _TIMEOUT_S,
        )
    except (OSError, TimeoutError):
        res.problems.append("does not resolve")
        return res
    ips = [i[4][0] for i in infos]
    if not ips or any(_is_blocked_ip(ip) for ip in ips):
        res.problems.append("resolves to a non-public address")
        return res
    res.ip = ips[0]

    try:
        obj, res.latency_ms = await _handshake(res.ip, port, host, verify=True)
        res.cert_valid = True
    except ssl.SSLCertVerificationError:
        res.problems.append("certificate not valid for this name")
        try:
            obj, res.latency_ms = await _handshake(res.ip, port, host, verify=False)
        except (OSError, TimeoutError, ssl.SSLError):
            res.problems.append("no TLS 1.3")
            return res
    except (OSError, TimeoutError, ssl.SSLError):
        res.problems.append("no TLS 1.3 handshake (or unreachable)")
        return res

    res.tls13 = obj.get("version") == "TLSv1.3"
    res.h2 = obj.get("alpn") == "h2"
    res.issuer = obj.get("issuer")
    if not res.h2:
        res.problems.append("no h2 (ALPN)")

    try:
        await _handshake(res.ip, port, host, verify=False, curve="X25519")
        res.x25519 = True
    except (ssl.SSLError, ValueError):
        res.x25519 = False
        res.problems.append("no X25519")
    except (OSError, TimeoutError):
        res.x25519 = None

    res.ok = res.tls13 and res.h2 and res.cert_valid and res.x25519 is not False
    return res


async def scan(targets: list[str]) -> list[ScanResult]:
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def guarded(t: str) -> ScanResult:
        async with sem:
            return await scan_one(t)

    unique = list(dict.fromkeys(t for t in targets if t.strip()))[:MAX_TARGETS]
    results = await asyncio.gather(*(guarded(t) for t in unique))
    return sorted(
        results, key=lambda r: (not r.ok, r.latency_ms if r.latency_ms is not None else 1e9)
    )
