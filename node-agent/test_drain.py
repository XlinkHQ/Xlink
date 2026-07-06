import importlib.util

spec = importlib.util.spec_from_file_location("a", "xlink-agent.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def _patch_apply(applied):
    m.DRY_RUN = False
    m._last_version = None
    m._last_active_kinds = set()
    m._core_hash = {}
    m._core_hash_reset = m._core_hash

    def fake(kind, core, core_clients):
        applied.append((kind, len(core_clients)))
        return True

    m.apply_one = fake


def test_drained_core_reloaded_when_last_client_removed():
    applied = []
    _patch_apply(applied)

    clients = [{"provider_kind": "xray", "protocol": "vless", "assignment_id": "a1", "settings": {}}]
    m.apply_config(clients, "v1")
    assert ("xray", 1) in applied
    assert m._last_active_kinds == {"xray"}

    applied.clear()
    m.apply_config([], "v2")
    assert applied == [("xray", 0)], applied
    assert m._last_active_kinds == set()


def test_first_run_forces_xray_even_if_empty():
    applied = []
    _patch_apply(applied)
    m.apply_config([], "v1")
    assert ("xray", 0) in applied


def test_no_reload_when_config_unchanged():
    applied = []
    _patch_apply(applied)
    clients = [{"provider_kind": "xray", "assignment_id": "a", "protocol": "vless", "settings": {}}]
    m.apply_config(clients, "v1")
    applied.clear()
    m.apply_config(clients, "v1")
    assert applied == [], applied


def test_effective_core_native():
    assert m._effective_core({"provider_kind": "xray", "protocol": "vless"}) == "xray"
    assert m._effective_core({"provider_kind": "sing-box", "protocol": "vless"}) == "sing-box"
    assert m._effective_core({"provider_kind": "hysteria", "protocol": "hysteria2"}) == "hysteria"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
