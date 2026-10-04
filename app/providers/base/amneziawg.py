"""AmneziaWG obfuscation parameters (AWG 1.x), shared by every layer.

Jc/Jmin/Jmax shape the junk packets a client sends before the handshake;
S1/S2 pad the handshake messages and H1-H4 replace WireGuard's fixed message
type headers, which is what DPI fingerprints. S1, S2 and H1-H4 must be
identical on server and client.
"""

from __future__ import annotations

import secrets

PARAMS = ("Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4")
_H_MIN = 5
_H_MAX = 2**32 - 1


def enabled(settings: dict) -> bool:
    return str(settings.get("amnezia", "")).strip().lower() in ("1", "true", "yes", "on")


def generate() -> dict[str, str]:
    jmin = 40 + secrets.randbelow(20)
    s1 = 15 + secrets.randbelow(136)
    s2 = 15 + secrets.randbelow(136)
    while s1 + 56 == s2:
        s2 = 15 + secrets.randbelow(136)
    headers: set[int] = set()
    while len(headers) < 4:
        headers.add(_H_MIN + secrets.randbelow(_H_MAX - _H_MIN))
    h1, h2, h3, h4 = sorted(headers)
    return {
        "Jc": str(4 + secrets.randbelow(9)),
        "Jmin": str(jmin),
        "Jmax": str(jmin + 30 + secrets.randbelow(900)),
        "S1": str(s1),
        "S2": str(s2),
        "H1": str(h1),
        "H2": str(h2),
        "H3": str(h3),
        "H4": str(h4),
    }


def problems(settings: dict) -> list[str]:
    vals: dict[str, int] = {}
    out: list[str] = []
    for k in PARAMS:
        raw = str(settings.get(k, "")).strip()
        if not raw.isdigit():
            out.append(f"{k} is required (a whole number)")
            continue
        vals[k] = int(raw)
    if out:
        return out
    if not 1 <= vals["Jc"] <= 128:
        out.append("Jc must be 1-128")
    if not 0 <= vals["Jmin"] < vals["Jmax"] <= 1280:
        out.append("need 0 <= Jmin < Jmax <= 1280")
    if vals["S1"] > 1132 or vals["S2"] > 1188:
        out.append("S1 must be <= 1132 and S2 <= 1188")
    if vals["S1"] + 56 == vals["S2"]:
        out.append("S1 + 56 must not equal S2")
    hs = [vals[f"H{i}"] for i in range(1, 5)]
    if len(set(hs)) != 4 or any(not _H_MIN <= h <= _H_MAX for h in hs):
        out.append(f"H1-H4 must be distinct and between {_H_MIN} and {_H_MAX}")
    return out
