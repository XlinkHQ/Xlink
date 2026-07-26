#!/usr/bin/env python3
"""Generate mTLS material for the XLink gRPC channel.

Usage:
  python gen-mtls.py ca                       -> ca.crt, ca.key
  python gen-mtls.py server <panel-host>      -> server.crt, server.key (signed by CA)
  python gen-mtls.py node <node-id>           -> <node-id>.crt, <node-id>.key (client, signed by CA)

Run in a directory holding ca.crt/ca.key for the server/node subcommands.
Panel: point XLINK_GRPC_TLS_CERT=server.crt, XLINK_GRPC_TLS_KEY=server.key,
       XLINK_GRPC_TLS_CA=ca.crt (requires client certs => mTLS).
Agent: XLINK_GRPC_TLS=1, XLINK_GRPC_TLS_CA=ca.crt,
       XLINK_GRPC_TLS_CERT=<node>.crt, XLINK_GRPC_TLS_KEY=<node>.key
"""

from __future__ import annotations

import datetime
import ipaddress
import os
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

_DAY = datetime.timedelta(days=1)


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _write(name: str, cert: x509.Certificate, key) -> None:
    key_path = f"{name}.key"
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
    with open(f"{name}.crt", "wb") as fh:
        fh.write(cert.public_bytes(serialization.Encoding.PEM))
    print(f"wrote {name}.crt {name}.key")


def _now():
    return datetime.datetime.now(datetime.UTC)


def make_ca() -> None:
    key = _key()
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "XLink gRPC CA")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() - _DAY)
        .not_valid_after(_now() + _DAY * 3650)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    _write("ca", cert, key)


def _load_ca():
    with open("ca.key", "rb") as fh:
        ca_key = serialization.load_pem_private_key(fh.read(), password=None)
    with open("ca.crt", "rb") as fh:
        ca_cert = x509.load_pem_x509_certificate(fh.read())
    return ca_key, ca_cert


def make_leaf(name: str, cn: str, san_dns: str | None) -> None:
    ca_key, ca_cert = _load_ca()
    key = _key()
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() - _DAY)
        .not_valid_after(_now() + _DAY * 825)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    )
    if san_dns:
        try:
            san = x509.IPAddress(ipaddress.ip_address(san_dns))
        except ValueError:
            san = x509.DNSName(san_dns)
        builder = builder.add_extension(x509.SubjectAlternativeName([san]), critical=False)
    cert = builder.sign(ca_key, hashes.SHA256())
    _write(name, cert, key)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "ca":
        make_ca()
    elif cmd == "server":
        if len(argv) < 3:
            print("server <panel-host>")
            return 2
        make_leaf("server", argv[2], argv[2])
    elif cmd == "node":
        if len(argv) < 3:
            print("node <node-id>")
            return 2
        make_leaf(argv[2], f"node:{argv[2]}", None)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
