import importlib.util
import json

spec = importlib.util.spec_from_file_location("a", "xlink-agent.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_hysteria_traffic_parse():
    m._http_get_json = lambda *a, **k: {"u1": {"tx": 100, "rx": 200}, "u2": {"tx": 0, "rx": 0}}
    out = m._hysteria_traffic()
    assert len(out) == 1
    assert out[0]["assignment_id"] == "u1"
    assert out[0]["upload_bytes"] == 100
    assert out[0]["download_bytes"] == 200


def test_singbox_traffic_statsquery(monkeypatch=None):
    import subprocess

    payload = json.dumps(
        {
            "stat": [
                {"name": "user>>>u1>>>traffic>>>uplink", "value": 500},
                {"name": "user>>>u1>>>traffic>>>downlink", "value": 1000},
            ]
        }
    ).encode()
    orig = subprocess.check_output
    subprocess.check_output = lambda *a, **k: payload
    try:
        out = m._singbox_traffic()
    finally:
        subprocess.check_output = orig
    assert out[0]["assignment_id"] == "u1"
    assert out[0]["upload_bytes"] == 500
    assert out[0]["download_bytes"] == 1000


def test_wireguard_maps_peer_and_deltas():
    import subprocess

    m._wg_prev.clear()
    clients = [{"assignment_id": "A1", "credentials": {"public_key": "PUB1"}}]
    orig = subprocess.check_output
    subprocess.check_output = lambda *a, **k: b"PUB1\t1000\t2000\n"
    try:
        out1 = m._wireguard_traffic(clients)
        assert out1[0]["assignment_id"] == "A1"
        assert out1[0]["upload_bytes"] == 1000
        assert out1[0]["download_bytes"] == 2000
        subprocess.check_output = lambda *a, **k: b"PUB1\t1500\t2000\n"
        out2 = m._wireguard_traffic(clients)
        assert out2[0]["upload_bytes"] == 500
        assert out2[0]["download_bytes"] == 0
    finally:
        subprocess.check_output = orig


def test_wireguard_unknown_peer_skipped():
    import subprocess

    m._wg_prev.clear()
    orig = subprocess.check_output
    subprocess.check_output = lambda *a, **k: b"OTHER\t10\t10\n"
    try:
        assert m._wireguard_traffic([{"assignment_id": "A1", "credentials": {"public_key": "PUB1"}}]) == []
    finally:
        subprocess.check_output = orig


def test_traffic_query_failure_returns_empty():
    def boom(*a, **k):
        raise OSError("refused")

    m._http_get_json = boom
    assert m._hysteria_traffic() == []


def test_client_id_prefers_credentials_uuid():
    cl = {
        "protocol": "vless",
        "credentials": {"uuid": "C1"},
        "settings": {"uuid": "S1"},
        "provider_client_id": "P1",
        "assignment_id": "A1",
    }
    assert m._client_id(cl) == "C1"


def test_client_id_falls_back_to_settings_uuid():
    cl = {"protocol": "vless", "credentials": {}, "settings": {"uuid": "S1"}, "assignment_id": "A1"}
    assert m._client_id(cl) == "S1"


def test_client_id_trojan_prefers_credentials_password():
    cl = {"protocol": "trojan", "credentials": {"password": "CPW"}, "settings": {}, "assignment_id": "A1"}
    assert m._client_id(cl) == "CPW"


def test_client_id_fallback_chain():
    assert m._client_id({"protocol": "vless", "settings": {}, "provider_client_id": "P1"}) == "P1"
    assert m._client_id({"protocol": "vless", "settings": {}, "assignment_id": "A1"}) == "A1"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
