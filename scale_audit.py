from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import time
import uuid

import psutil

os.environ.setdefault("XLINK_ENV", "testing")
os.environ.setdefault("XLINK_JWT_SECRET_KEY", "audit-secret-key-32-chars-minimum-9xx")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.base import Base
import app.domain  # noqa: F401

PROC = psutil.Process()
DB_PATH = os.environ.get("AUDIT_DB", "/tmp/xlink_audit.sqlite")


def rss_mb() -> float:
    return PROC.memory_info().rss / 1024 / 1024


def disk_free_gb() -> float:
    return psutil.disk_usage("/").free / 1024 / 1024 / 1024


def db_size_mb() -> float:
    total = 0
    for suffix in ("", "-wal", "-shm"):
        p = DB_PATH + suffix
        if os.path.exists(p):
            total += os.path.getsize(p)
    return total / 1024 / 1024


def check_stops(label: str) -> None:
    free = disk_free_gb()
    vm = psutil.virtual_memory()
    if free < 3.0:
        raise SystemExit(f"STOP[{label}]: disk free {free:.1f}GB < 3GB safety floor")
    if vm.percent > 92.0:
        raise SystemExit(f"STOP[{label}]: RAM {vm.percent:.0f}% > 92% safety ceiling")
    swap = psutil.swap_memory()
    if swap.percent > 80.0 and swap.total > 2 * 1024**3:
        raise SystemExit(f"STOP[{label}]: swap {swap.percent:.0f}% > 80%")


async def reset_db(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


def _uid() -> str:
    return str(uuid.uuid4())


async def seed(engine, n_users, n_nodes, n_profiles, n_assignments, batch=5000):
    raw = await engine.raw_connection()
    conn = raw.driver_connection
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")

    user_ids, node_ids, profile_ids = [], [], []
    t0 = time.perf_counter()

    rows = []
    for i in range(n_users):
        uid = _uid()
        user_ids.append(uid)
        rows.append((uid, f"u{i}@audit.io", f"user{i}", "x" * 20, None, "user", 1, 0))
        if len(rows) >= batch:
            await conn.executemany(
                "INSERT INTO users (id,email,username,hashed_password,full_name,role,is_active,is_verified,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))",
                rows,
            )
            rows.clear()
            check_stops("seed-users")
    if rows:
        await conn.executemany(
            "INSERT INTO users (id,email,username,hashed_password,full_name,role,is_active,is_verified,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))",
            rows,
        )
        rows.clear()
    t_users = time.perf_counter() - t0

    t0 = time.perf_counter()
    for i in range(n_nodes):
        nid = _uid()
        node_ids.append(nid)
        rows.append(
            (
                nid,
                f"node{i}",
                f"node-{i}",
                f"10.0.{i // 256}.{i % 256}",
                443,
                "active",
                1000,
                0,
                "{}",
                1,
            )
        )
    await conn.executemany(
        "INSERT INTO nodes (id,name,slug,host,port,status,max_users,current_users,metadata,version,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))",
        rows,
    )
    rows.clear()
    t_nodes = time.perf_counter() - t0

    t0 = time.perf_counter()
    for i in range(n_profiles):
        pid = _uid()
        profile_ids.append(pid)
        nid = node_ids[i % len(node_ids)]
        rows.append((pid, f"profile{i}", f"prof-{i}", "xray", nid, "vless", "{}", 1, 1))
        if len(rows) >= batch:
            await conn.executemany(
                "INSERT INTO profiles (id,name,slug,provider_kind,node_id,protocol,settings,is_active,version,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))",
                rows,
            )
            rows.clear()
            check_stops("seed-profiles")
    if rows:
        await conn.executemany(
            "INSERT INTO profiles (id,name,slug,provider_kind,node_id,protocol,settings,is_active,version,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))",
            rows,
        )
        rows.clear()
    t_profiles = time.perf_counter() - t0

    t0 = time.perf_counter()
    inserted = 0
    nprof = len(profile_ids)
    profile_node = {pid: node_ids[k % len(node_ids)] for k, pid in enumerate(profile_ids)}
    for i in range(n_assignments):
        aid = _uid()
        uid = user_ids[i % len(user_ids)]
        pid = profile_ids[(i // len(user_ids)) % nprof]
        nid = profile_node[pid]
        status = "active" if i % 5 else "disabled"
        rows.append((aid, uid, pid, nid, "xray", f"xc-{i}", status, None, None, 1))
        if len(rows) >= batch:
            await conn.executemany(
                "INSERT INTO client_assignments (id,user_id,profile_id,node_id,provider_kind,provider_client_id,status,expires_at,traffic_limit_bytes,version,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now','-'||abs(random()%100000)||' seconds'),datetime('now'))",
                rows,
            )
            inserted += len(rows)
            rows.clear()
            check_stops("seed-assignments")
    if rows:
        await conn.executemany(
            "INSERT INTO client_assignments (id,user_id,profile_id,node_id,provider_kind,provider_client_id,status,expires_at,traffic_limit_bytes,version,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now','-'||abs(random()%100000)||' seconds'),datetime('now'))",
            rows,
        )
        inserted += len(rows)
        rows.clear()
    await conn.commit()
    t_assign = time.perf_counter() - t0

    raw.close()
    return {
        "t_users": t_users,
        "t_nodes": t_nodes,
        "t_profiles": t_profiles,
        "t_assign": t_assign,
        "assign_rows": inserted,
    }


async def bench_query(engine, sql, params=None, repeat=30):
    samples = []
    async with engine.connect() as conn:
        for _ in range(3):
            await conn.execute(text(sql), params or {})
        for _ in range(repeat):
            t0 = time.perf_counter()
            res = await conn.execute(text(sql), params or {})
            res.fetchall()
            samples.append((time.perf_counter() - t0) * 1000)
    samples.sort()
    return {
        "p50": statistics.median(samples),
        "p95": samples[int(len(samples) * 0.95) - 1],
        "p99": samples[min(int(len(samples) * 0.99), len(samples) - 1)],
        "max": samples[-1],
    }


async def explain(engine, sql, params=None):
    async with engine.connect() as conn:
        res = await conn.execute(text("EXPLAIN QUERY PLAN " + sql), params or {})
        return [r[-1] for r in res.fetchall()]


async def run_level(name, n_users, n_nodes, n_profiles, n_assignments):
    if os.path.exists(DB_PATH):
        for s in ("", "-wal", "-shm"):
            try:
                os.remove(DB_PATH + s)
            except FileNotFoundError:
                pass
    engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}")
    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")
    print(f"baseline RSS={rss_mb():.0f}MB diskFree={disk_free_gb():.1f}GB")
    await reset_db(engine)
    rss_before = rss_mb()

    s = await seed(engine, n_users, n_nodes, n_profiles, n_assignments)
    rss_after = rss_mb()
    print(
        f"SEED users={n_users}({s['t_users']:.2f}s) nodes={n_nodes}({s['t_nodes']:.3f}s) "
        f"profiles={n_profiles}({s['t_profiles']:.2f}s) assign={s['assign_rows']}({s['t_assign']:.2f}s)"
    )
    rate = s["assign_rows"] / s["t_assign"] if s["t_assign"] else 0
    print(f"     assignment insert rate = {rate:,.0f} rows/s")
    print(
        f"     dbSize={db_size_mb():.1f}MB  RSS {rss_before:.0f}->{rss_after:.0f}MB  diskFree={disk_free_gb():.1f}GB"
    )

    async with engine.connect() as c:
        sample_node = (
            await c.execute(text("SELECT node_id FROM client_assignments LIMIT 1"))
        ).scalar()
        sample_user = (
            await c.execute(text("SELECT user_id FROM client_assignments LIMIT 1"))
        ).scalar()
        row = (
            await c.execute(
                text(
                    "SELECT created_at,id FROM client_assignments ORDER BY created_at DESC, id DESC LIMIT 1 OFFSET 100"
                )
            )
        ).first()
        cur_created, cur_id = (row[0], row[1]) if row else ("now", "z")

    queries = {
        "keyset_page (list_keyset emulation)": (
            "SELECT * FROM client_assignments ORDER BY created_at DESC, id DESC LIMIT 50",
            None,
        ),
        "keyset_page_deep (row-value cursor)": (
            "SELECT * FROM client_assignments WHERE (created_at, id) < (:cc, :ci) "
            "ORDER BY created_at DESC, id DESC LIMIT 50",
            {"cc": cur_created, "ci": cur_id},
        ),
        "by_node (indexed FK)": (
            "SELECT * FROM client_assignments WHERE node_id = :nid LIMIT 50",
            {"nid": sample_node},
        ),
        "by_user (indexed FK)": (
            "SELECT * FROM client_assignments WHERE user_id = :uid LIMIT 50",
            {"uid": sample_user},
        ),
        "status_filter (indexed)": (
            "SELECT * FROM client_assignments WHERE status='active' ORDER BY created_at DESC, id DESC LIMIT 50",
            None,
        ),
        "count_all (full scan)": ("SELECT COUNT(*) FROM client_assignments", None),
        "active_count_by_node (agg)": (
            "SELECT node_id, COUNT(*) FROM client_assignments WHERE status='active' GROUP BY node_id",
            None,
        ),
    }
    print("  QUERY BENCHMARKS (ms):")
    plans = {}
    for label, (sql, params) in queries.items():
        b = await bench_query(engine, sql, params)
        plan = await explain(engine, sql, params)
        uses_index = any("USING INDEX" in p or "SEARCH" in p for p in plan)
        scan = any("SCAN" in p and "USING INDEX" not in p for p in plan)
        plans[label] = (uses_index, scan, plan)
        flag = "FULLSCAN" if scan else ("idx" if uses_index else "?")
        print(
            f"    {label:42s} p50={b['p50']:.2f} p95={b['p95']:.2f} p99={b['p99']:.2f} max={b['max']:.2f} [{flag}]"
        )
    await engine.dispose()
    return {"seed": s, "db_mb": db_size_mb(), "rss_delta": rss_after - rss_before}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, required=True)
    args = ap.parse_args()
    if args.level == 1:
        await run_level("LEVEL 1 — SMOKE SCALE", 1000, 10, 100, 10000)
    elif args.level == 2:
        await run_level("LEVEL 2 — LOCAL STRESS SCALE", 10000, 100, 1000, 100000)
    print(f"\nFINAL RSS={rss_mb():.0f}MB diskFree={disk_free_gb():.1f}GB")


if __name__ == "__main__":
    asyncio.run(main())
