import importlib.util

spec = importlib.util.spec_from_file_location("a", "xlink-agent.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def _reset():
    m._usage_acc.clear()
    m._over_users.clear()


def test_under_limit_kept():
    _reset()
    clients = [{"assignment_id": "a1", "user_id": "u1", "data_limit_bytes": 1000}]
    samples = [{"assignment_id": "a1", "upload_bytes": 100, "download_bytes": 100}]
    out = m._local_enforce(clients, samples)
    assert len(out) == 1


def test_over_limit_dropped():
    _reset()
    clients = [{"assignment_id": "a1", "user_id": "u1", "data_limit_bytes": 1000}]
    samples = [{"assignment_id": "a1", "upload_bytes": 600, "download_bytes": 600}]
    out = m._local_enforce(clients, samples)
    assert out == []
    assert "u1" in m._over_users


def test_base_usage_from_panel_triggers_without_delta():
    _reset()
    clients = [
        {"assignment_id": "a1", "user_id": "u1", "data_limit_bytes": 1000, "used_bytes": 1000}
    ]
    out = m._local_enforce(clients, [])
    assert out == []


def test_base_plus_small_delta_triggers():
    _reset()
    clients = [
        {"assignment_id": "a1", "user_id": "u1", "data_limit_bytes": 1000, "used_bytes": 950}
    ]
    out = m._local_enforce(clients, [{"assignment_id": "a1", "upload_bytes": 60, "download_bytes": 0}])
    assert out == []


def test_base_under_limit_kept():
    _reset()
    clients = [
        {"assignment_id": "a1", "user_id": "u1", "data_limit_bytes": 1000, "used_bytes": 500}
    ]
    out = m._local_enforce(clients, [{"assignment_id": "a1", "upload_bytes": 10, "download_bytes": 10}])
    assert len(out) == 1


def test_accumulates_across_cycles():
    _reset()
    clients = [{"assignment_id": "a1", "user_id": "u1", "data_limit_bytes": 1000}]
    m._local_enforce(clients, [{"assignment_id": "a1", "upload_bytes": 400, "download_bytes": 0}])
    assert len(m._local_enforce(clients, [])) == 1
    out = m._local_enforce(clients, [{"assignment_id": "a1", "upload_bytes": 700, "download_bytes": 0}])
    assert out == []


def test_no_limit_never_dropped():
    _reset()
    clients = [{"assignment_id": "a1", "user_id": "u1", "data_limit_bytes": None}]
    samples = [{"assignment_id": "a1", "upload_bytes": 10**9, "download_bytes": 0}]
    assert len(m._local_enforce(clients, samples)) == 1


def test_multi_user_only_over_dropped():
    _reset()
    clients = [
        {"assignment_id": "a1", "user_id": "u1", "data_limit_bytes": 1000},
        {"assignment_id": "a2", "user_id": "u2", "data_limit_bytes": 1000},
    ]
    samples = [
        {"assignment_id": "a1", "upload_bytes": 2000, "download_bytes": 0},
        {"assignment_id": "a2", "upload_bytes": 10, "download_bytes": 0},
    ]
    out = m._local_enforce(clients, samples)
    assert [c["user_id"] for c in out] == ["u2"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
