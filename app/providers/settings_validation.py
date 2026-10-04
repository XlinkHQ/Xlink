from __future__ import annotations

import base64
import binascii
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

from app.core.exceptions import ValidationError
from app.providers.base.models import ProviderKind


def _require(settings: dict[str, Any], key: str, label: str) -> None:
    value = settings.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValidationError(f"{label} is required.", code="profile_settings_invalid")


def _port(settings: dict[str, Any]) -> None:
    port = settings.get("port")
    if port is None:
        return
    try:
        p = int(port)
    except (TypeError, ValueError) as exc:
        raise ValidationError("port must be a number.", code="profile_settings_invalid") from exc
    if not (1 <= p <= 65535):
        raise ValidationError("port must be between 1 and 65535.", code="profile_settings_invalid")


def _validate_security(settings: dict[str, Any]) -> None:
    security = str(settings.get("security", "none")).strip().lower()
    if security == "tls":
        if not (settings.get("sni") or settings.get("host")):
            raise ValidationError(
                "TLS requires an SNI (server name).", code="profile_settings_invalid"
            )
    elif security == "reality":
        if not (settings.get("publicKey") or settings.get("pbk")):
            raise ValidationError("REALITY requires a publicKey.", code="profile_settings_invalid")
        if not settings.get("sni"):
            raise ValidationError(
                "REALITY requires an SNI (server name).", code="profile_settings_invalid"
            )


def _validate_singbox(protocol: str, settings: dict[str, Any]) -> None:
    _port(settings)
    _validate_security(settings)
    if protocol == "hysteria2" and not (settings.get("password") or settings.get("obfs")):
        return


def _validate_hysteria(protocol: str, settings: dict[str, Any]) -> None:
    _port(settings)
    if not (settings.get("sni") or settings.get("host") or settings.get("obfs")):
        return


def _wg_key_bytes(settings: dict[str, Any], key: str, label: str) -> bytes:
    _require(settings, key, label)
    raw = str(settings[key]).strip()
    try:
        decoded = base64.standard_b64decode(raw)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError(
            f"{label} is not valid base64.", code="profile_settings_invalid"
        ) from exc
    if len(decoded) != 32:
        raise ValidationError(
            f"{label} must be a 32-byte WireGuard key.", code="profile_settings_invalid"
        )
    return decoded


def _validate_wireguard(protocol: str, settings: dict[str, Any]) -> None:
    _port(settings)
    _require(settings, "address", "Interface address")
    priv = _wg_key_bytes(settings, "privateKey", "Server private key")
    _wg_key_bytes(settings, "publicKey", "Server public key")

    derived = base64.standard_b64encode(
        x25519.X25519PrivateKey.from_private_bytes(priv)
        .public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode("ascii")
    if derived != str(settings["publicKey"]).strip():
        raise ValidationError(
            "Server publicKey does not match privateKey — they must be a "
            "matching WireGuard key pair.",
            code="profile_settings_invalid",
        )
    _wg_mtu(settings)
    from app.providers.base import amneziawg

    if amneziawg.enabled(settings):
        issues = amneziawg.problems(settings)
        if issues:
            raise ValidationError(
                "AmneziaWG: " + "; ".join(issues) + ". Use Generate keys.",
                code="profile_settings_invalid",
            )


def _wg_mtu(settings: dict[str, Any]) -> None:
    """Reject an out-of-range MTU at save time.

    All three layers (panel store, node agent, client config) share the
    1280..1500 window. Accepting 9000 here and clamping it downstream meant the
    operator saw a successful save while the tunnel quietly used a different
    value, so this is a hard error rather than a silent correction.
    """
    raw = settings.get("mtu")
    if raw in (None, ""):
        return
    try:
        mtu = int(raw)
    except (TypeError, ValueError):
        raise ValidationError(
            "MTU must be a whole number.", code="profile_settings_invalid"
        ) from None
    if not (1280 <= mtu <= 1500):
        raise ValidationError(
            f"MTU must be between 1280 and 1500 (got {mtu}). 1420 suits most networks.",
            code="profile_settings_invalid",
        )


_HOSTNAME = __import__("re").compile(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)


def _validate_mtproto(protocol: str, settings: dict[str, Any]) -> None:
    """The node writes these into a Python config file that mtprotoproxy
    executes, so anything outside the strict shapes below is refused."""
    _port(settings)
    domain = str(settings.get("tlsDomain") or "").strip().lower()
    if not _HOSTNAME.match(domain):
        raise ValidationError(
            "tlsDomain must be a plain domain name (the site the fake-TLS mimics).",
            code="profile_settings_invalid",
        )
    tag = str(settings.get("adTag") or "").strip()
    if tag and (len(tag) != 32 or any(c not in "0123456789abcdef" for c in tag.lower())):
        raise ValidationError(
            "adTag must be the 32-hex tag from @MTProxybot.", code="profile_settings_invalid"
        )


_VALIDATORS = {
    ProviderKind.SING_BOX: _validate_singbox,
    ProviderKind.HYSTERIA: _validate_hysteria,
    ProviderKind.WIREGUARD: _validate_wireguard,
    ProviderKind.MTPROTO: _validate_mtproto,
}


# field -> (keys forbidden at the top level, keys forbidden at ANY depth).
# Mirrors node-agent _RAW_PROTECTED/_RAW_CREDENTIAL_KEYS and
# subscription/formats/raw_override._PROTECTED/_DEEP_PROTECTED.
_RAW_FIELDS = {
    "rawInbound": (
        frozenset({"tag", "listen", "port", "listen_port", "type", "protocol"}),
        frozenset({"clients", "users", "accounts", "password", "uuid"}),
    ),
    "rawClientOutbound": (
        frozenset({"tag", "type", "protocol", "server", "server_port"}),
        frozenset({"uuid", "password", "users", "vnext", "servers", "address", "port", "id"}),
    ),
}


def _deep_keys(value: Any, path: str = "") -> list[tuple[str, str]]:
    """(key, dotted path) for every dict key at every depth."""
    out: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for k, v in value.items():
            here = f"{path}.{k}" if path else k
            out.append((k, here))
            out += _deep_keys(v, here)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            out += _deep_keys(item, f"{path}[{i}]")
    return out
_RAW_MAX_BYTES = 16 * 1024


def _validate_raw_overrides(settings: dict[str, Any]) -> None:
    """Passthrough overrides are validated up front so a bad one fails the save
    instead of being half-applied (or silently dropped) on the node."""
    import json

    for field, (protected, deep_protected) in _RAW_FIELDS.items():
        raw = settings.get(field)
        if raw in (None, "", {}):
            continue
        if not isinstance(raw, dict):
            raise ValidationError(
                f"{field} must be a JSON object.", code="profile_settings_invalid"
            )
        try:
            size = len(json.dumps(raw))
        except (TypeError, ValueError):
            raise ValidationError(
                f"{field} must be plain JSON.", code="profile_settings_invalid"
            ) from None
        if size > _RAW_MAX_BYTES:
            raise ValidationError(
                f"{field} is too large ({size} bytes, max {_RAW_MAX_BYTES}).",
                code="profile_settings_invalid",
            )
        # casefold: the consumers are Go (encoding/json matches case-insensitively).
        clash = sorted(k for k in raw if str(k).casefold() in protected)
        clash += sorted(p for k, p in _deep_keys(raw) if str(k).casefold() in deep_protected)
        if clash:
            raise ValidationError(
                f"{field} may not set {', '.join(clash)} — the panel manages those.",
                code="profile_settings_invalid",
            )


_ALPN_VALUES = frozenset({"h3", "h2", "http/1.1"})
_TUIC_CONGESTION = frozenset({"bbr", "cubic", "new_reno"})


def _bad(msg: str) -> ValidationError:
    return ValidationError(msg, code="profile_settings_invalid")


def _validate_common(protocol: str, settings: dict[str, Any]) -> None:
    """Checks that hold whatever core serves the profile. Each of these used
    to be accepted here and then rejected by the core on the node (freezing
    the node on its previous config) or by the client at connect time."""
    from app.providers.base import ss2022

    if protocol in ("shadowsocks", "shadowsocks2022"):
        method = ss2022.method_for(protocol, settings)
        if ss2022.is_2022(method):
            n = ss2022.key_bytes(method)
            server = settings.get("serverPassword")
            if not server:
                raise _bad(
                    f"{method} needs a serverPassword (base64 of {n} random bytes). "
                    "Use Generate keys."
                )
            if not ss2022.key_ok(server, method):
                raise _bad(f"serverPassword must be base64 of exactly {n} bytes for {method}.")
            pw = settings.get("password")
            if pw and not ss2022.key_ok(pw, method):
                raise _bad(f"password must be base64 of exactly {n} bytes for {method}.")

    if str(settings.get("security", "")).strip().lower() == "reality":
        short = str(settings.get("shortId") or "").strip()
        if short and (
            len(short) > 16
            or len(short) % 2
            or any(c not in "0123456789abcdefABCDEF" for c in short)
        ):
            raise _bad("REALITY shortId must be hex, an even length, at most 16 characters.")
        priv = str(settings.get("privateKey") or "").strip()
        pub = str(settings.get("publicKey") or settings.get("pbk") or "").strip()
        if priv and pub:
            try:
                raw = base64.urlsafe_b64decode(priv + "=" * (-len(priv) % 4))
                derived = (
                    base64.urlsafe_b64encode(
                        x25519.X25519PrivateKey.from_private_bytes(raw)
                        .public_key()
                        .public_bytes(
                            serialization.Encoding.Raw, serialization.PublicFormat.Raw
                        )
                    )
                    .rstrip(b"=")
                    .decode()
                )
            except (binascii.Error, ValueError):
                raise _bad("REALITY privateKey is not a valid X25519 key.") from None
            if derived != pub.rstrip("="):
                raise _bad(
                    "REALITY publicKey does not match privateKey — every client would "
                    "fail the handshake. Regenerate the pair."
                )

    alpn = settings.get("alpn")
    if alpn:
        items = alpn if isinstance(alpn, list) else str(alpn).split(",")
        unknown = [a for a in (str(x).strip() for x in items) if a and a not in _ALPN_VALUES]
        if unknown:
            raise _bad(f"Unknown ALPN value(s): {', '.join(unknown)} (use h3, h2, http/1.1).")

    if protocol == "tuic":
        cc = str(settings.get("congestionControl") or "bbr").strip().lower()
        if cc not in _TUIC_CONGESTION:
            raise _bad("TUIC congestionControl must be bbr, cubic or new_reno.")


def validate_profile_settings(
    kind: ProviderKind, protocol: str, settings: dict[str, Any] | None
) -> None:
    _validate_raw_overrides(settings or {})
    _validate_common(str(protocol or "").strip().lower(), settings or {})
    validator = _VALIDATORS.get(kind)
    if validator is None:
        return
    validator(str(protocol or "").strip().lower(), settings or {})
