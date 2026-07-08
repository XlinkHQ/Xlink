"""Regression tests for two high-risk, previously untested node-agent paths:

1. The traffic write-ahead log (WAL) rotate/commit accounting. This is the
   "no byte of usage is lost across a crash/outage" guarantee: deltas are
   persisted before the core stats reset and only dropped after the panel acks
   the delivered count. An off-by-one between "delivered" and "dropped" would
   silently double-count or discard traffic. Nothing tested it before.

2. The upgrade command `target_version` sanitizer in _run_command — a
   defense-in-depth shell-injection guard with no prior test.
"""

import importlib.util
import json
import os

_AGENT = os.path.join(os.path.dirname(__file__), "xlink-agent.py")
os.environ.setdefault("XLINK_PANEL_URL", "http://x")
os.environ.setdefault("XLINK_NODE_ID", "n")
os.environ.setdefault("XLINK_AGENT_TOKEN", "t")
spec = importlib.util.spec_from_file_location("xlink_agent_under_test", _AGENT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def _point_wal_at(tmp_path):
    """Redirect the module-global WAL paths at a temp dir for isolation."""
    wal = os.path.join(str(tmp_path), "traffic.wal")
    m.WAL_PATH = wal
    m._WAL_INFLIGHT = wal + ".inflight"
    return wal


def _sample(i):
    return {"assignment_id": f"a{i}", "upload_bytes": i, "download_bytes": i * 2}


def test_wal_append_then_rotate_returns_all(tmp_path):
    _point_wal_at(tmp_path)
    m._wal_append([_sample(1), _sample(2), _sample(3)])
    rotated = m._wal_rotate()
    assert [s["assignment_id"] for s in rotated] == ["a1", "a2", "a3"]


def test_wal_commit_drops_only_delivered_oldest(tmp_path):
    _point_wal_at(tmp_path)
    m._wal_append([_sample(1), _sample(2), _sample(3)])
    rotated = m._wal_rotate()
    assert len(rotated) == 3
    # Panel acked only the first 2 (FIFO). The third must survive for next cycle.
    m._wal_commit(2)
    remaining = m._read_wal_file(m._WAL_INFLIGHT)
    assert [s["assignment_id"] for s in remaining] == ["a3"]


def test_wal_commit_all_removes_inflight(tmp_path):
    _point_wal_at(tmp_path)
    m._wal_append([_sample(1), _sample(2)])
    m._wal_rotate()
    m._wal_commit(2)
    assert not os.path.exists(m._WAL_INFLIGHT)


def test_wal_append_during_delivery_not_lost(tmp_path):
    """Core invariant: a sample appended AFTER rotate (i.e. during delivery) lands
    in a fresh WAL and must not be destroyed when the delivered batch is committed."""
    _point_wal_at(tmp_path)
    m._wal_append([_sample(1), _sample(2)])
    rotated = m._wal_rotate()  # claims a1,a2 into .inflight
    assert len(rotated) == 2
    # Fast-enforce loop appends a new sample concurrently with delivery.
    m._wal_append([_sample(9)])
    # Panel acks the 2 delivered; the new sample must remain in the live WAL.
    m._wal_commit(2)
    # Next rotate must fold the live WAL back in and surface the survivor.
    next_rotated = m._wal_rotate()
    assert [s["assignment_id"] for s in next_rotated] == ["a9"]


def test_wal_rotate_folds_leftover_inflight(tmp_path):
    """A crash mid-delivery leaves an .inflight file; the next rotate must fold the
    new WAL into it (not overwrite) so the un-acked backlog is preserved."""
    _point_wal_at(tmp_path)
    # Simulate leftover un-acked inflight from a prior crash.
    with open(m._WAL_INFLIGHT, "w") as fh:
        fh.write(json.dumps(_sample(1)) + "\n")
    # New usage accumulates in the live WAL.
    m._wal_append([_sample(2)])
    rotated = m._wal_rotate()
    ids = sorted(s["assignment_id"] for s in rotated)
    assert ids == ["a1", "a2"]  # both the leftover and the new one


def test_wal_rotate_fifo_caps_at_wal_max(tmp_path):
    _point_wal_at(tmp_path)
    m._WAL_MAX = 5
    try:
        m._wal_append([_sample(i) for i in range(10)])
        rotated = m._wal_rotate()
        # Oldest _WAL_MAX delivered first (FIFO), tail retained.
        assert [s["assignment_id"] for s in rotated] == [f"a{i}" for i in range(5)]
    finally:
        m._WAL_MAX = 20000


# --- upgrade target_version sanitizer -------------------------------------


def test_upgrade_rejects_injection_in_target_version():
    ok, result = m._run_command(
        "upgrade", {"core": "xray", "target_version": "1.2.3; rm -rf /"}
    )
    assert ok is False
    assert "invalid target_version" in result["error"]


def test_upgrade_rejects_shell_metachars():
    for bad in ["$(id)", "`whoami`", "1.0 && curl evil", "v1|cat"]:
        ok, result = m._run_command("upgrade", {"core": "xray", "target_version": bad})
        assert ok is False, f"expected rejection for {bad!r}"
        assert "invalid target_version" in result["error"]


def test_upgrade_unknown_core_rejected():
    ok, result = m._run_command("upgrade", {"core": "definitely-not-a-core"})
    assert ok is False
    assert "unknown or missing core" in result["error"]


def test_run_command_unsupported_kind():
    ok, result = m._run_command("nonsense", {})
    assert ok is False
    assert "unsupported command kind" in result["error"]
