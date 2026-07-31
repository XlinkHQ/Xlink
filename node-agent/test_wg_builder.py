import base64
import importlib.util
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("wga", os.path.join(_HERE, "xlink-agent.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def _key():
    return base64.b64encode(os.urandom(32)).decode()


def test_foreign_wg_profile_clients_skipped():
    priv_a, priv_b = _key(), _key()
    clients = [
        {
            "settings": {"privateKey": priv_a, "port": 51820, "address": "10.8.0.1/24"},
            "credentials": {"public_key": _key(), "address": "10.8.0.2/32"},
        },
        {
            "settings": {"privateKey": priv_b, "port": 51820, "address": "10.9.0.1/24"},
            "credentials": {"public_key": _key(), "address": "10.9.0.2/32"},
        },
    ]
    conf = m.build_wireguard_config(clients)
    assert conf.count("[Peer]") == 1


def test_peer_without_address_skipped():
    priv = _key()
    clients = [
        {
            "settings": {"privateKey": priv, "port": 51820, "address": "10.8.0.1/24"},
            "credentials": {"public_key": _key(), "address": "10.8.0.2/32"},
        },
        {
            "settings": {"privateKey": priv, "port": 51820, "address": "10.8.0.1/24"},
            "credentials": {"public_key": _key()},
        },
    ]
    conf = m.build_wireguard_config(clients)
    assert conf.count("[Peer]") == 1


def test_server_ip_not_used_as_peer():
    priv = _key()
    clients = [
        {
            "settings": {"privateKey": priv, "port": 51820, "address": "10.8.0.1/24"},
            "credentials": {"public_key": _key(), "address": "10.8.0.1/32"},
        },
    ]
    conf = m.build_wireguard_config(clients)
    assert conf.count("[Peer]") == 0
