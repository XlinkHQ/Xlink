"""IP → ASN from the public iptoasn.com dataset (public domain, updated hourly).

Kept local and in memory so a subscription fetch never waits on a remote
lookup. Ranges live in compact ``array`` columns (≈6 MB for IPv4); IPv6 is
indexed by the top 64 bits, which is exact for anything routed on the
Internet (BGP does not carry prefixes longer than /48).
"""

from __future__ import annotations

import asyncio
import gzip
import ipaddress
import os
import time
import urllib.request
from array import array
from bisect import bisect_right
from dataclasses import dataclass, field

from app.core.logging import get_logger

logger = get_logger("xlink.asn")

SOURCES = {
    "v4": "https://iptoasn.com/data/ip2asn-v4.tsv.gz",
    "v6": "https://iptoasn.com/data/ip2asn-v6.tsv.gz",
}
_MAX_DOWNLOAD = 64 * 1024 * 1024
_RECHECK_S = 60.0


@dataclass
class _Table:
    starts: array
    ends: array
    asns: array

    def find(self, key: int) -> int | None:
        i = bisect_right(self.starts, key) - 1
        if i < 0 or key > self.ends[i]:
            return None
        asn = self.asns[i]
        return asn or None  # AS0 = "not routed"


def _parse(path: str, v6: bool) -> _Table:
    code = "Q" if v6 else "I"
    starts, ends, asns = array(code), array(code), array("I")
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.split("\t", 3)
            if len(parts) < 3:
                continue
            try:
                lo = int(ipaddress.ip_address(parts[0]))
                hi = int(ipaddress.ip_address(parts[1]))
                asn = int(parts[2])
            except ValueError:
                continue
            if v6:
                lo, hi = lo >> 64, hi >> 64
            starts.append(lo)
            ends.append(hi)
            asns.append(asn)
    return _Table(starts, ends, asns)


@dataclass
class AsnDatabase:
    directory: str
    _tables: dict[str, _Table] = field(default_factory=dict)
    _mtimes: dict[str, float] = field(default_factory=dict)
    _checked: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def path(self, family: str) -> str:
        return os.path.join(self.directory, f"ip2asn-{family}.tsv.gz")

    async def _refresh(self) -> None:
        now = time.monotonic()
        if now - self._checked < _RECHECK_S:
            return
        async with self._lock:
            if now - self._checked < _RECHECK_S:
                return
            self._checked = now
            for family in ("v4", "v6"):
                p = self.path(family)
                try:
                    mtime = os.path.getmtime(p)  # noqa: ASYNC240 - one stat per minute
                except OSError:
                    self._tables.pop(family, None)
                    continue
                if self._mtimes.get(family) == mtime:
                    continue
                try:
                    self._tables[family] = await asyncio.to_thread(_parse, p, family == "v6")
                    self._mtimes[family] = mtime
                    logger.info(
                        "asn_db_loaded", family=family, ranges=len(self._tables[family].starts)
                    )
                except (OSError, EOFError) as exc:
                    logger.warning("asn_db_load_failed", family=family, error=str(exc))

    async def lookup(self, ip: str) -> int | None:
        await self._refresh()
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return None
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped
        table = self._tables.get("v4" if addr.version == 4 else "v6")
        if table is None:
            return None
        key = int(addr) if addr.version == 4 else int(addr) >> 64
        return table.find(key)

    async def status(self) -> dict[str, object]:
        await self._refresh()
        return {
            family: {
                "ranges": len(t.starts),
                "updated_at": self._mtimes.get(family),
            }
            for family, t in self._tables.items()
        }

    async def download(self) -> dict[str, object]:
        """Fetch both files from the fixed iptoasn URLs (no caller-supplied
        URL, so this cannot be turned into an SSRF primitive)."""
        os.makedirs(self.directory, exist_ok=True)
        for family, url in SOURCES.items():
            await asyncio.to_thread(_fetch, url, self.path(family))
        self._checked = 0.0
        return await self.status()


def _fetch(url: str, dest: str) -> None:
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "xlink-panel"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:  # noqa: S310
        total = 0
        while chunk := resp.read(1 << 20):
            total += len(chunk)
            if total > _MAX_DOWNLOAD:
                raise ValueError("ASN dataset larger than expected")
            out.write(chunk)
    # Must be a readable gzip before it replaces the live file.
    with gzip.open(tmp, "rt") as fh:
        fh.readline()
    os.replace(tmp, dest)


_db: AsnDatabase | None = None


def get_db(directory: str) -> AsnDatabase:
    global _db
    if _db is None or _db.directory != directory:
        _db = AsnDatabase(directory)
    return _db
