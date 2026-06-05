from __future__ import annotations

import asyncio
import os
import statistics
import time

import psutil

os.environ["XLINK_ENV"] = "testing"
os.environ["XLINK_RATE_LIMIT_ENABLED"] = "false"
os.environ["XLINK_JWT_SECRET_KEY"] = "audit-secret-key-32-chars-minimum-9xx"
os.environ.setdefault("XLINK_ARGON2_TIME_COST", "3")
os.environ.setdefault("XLINK_ARGON2_MEMORY_COST", "65536")
os.environ.setdefault("XLINK_ARGON2_PARALLELISM", "4")

import fakeredis.aioredis
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.lifespan import AppState
from app.db.base import Base
from app.db.redis import RedisCache
from app.db.session import Database
from app.events.bus import EventBus
from app.events.handlers import register_default_handlers
from app.events.registry import EventRegistry
from app.main import create_app
from app.providers.discovery import build_registry

PROC = psutil.Process()


def pct(samples, p):
    if not samples:
        return 0.0
    samples = sorted(samples)
    k = min(int(len(samples) * p), len(samples) - 1)
    return samples[k]


async def build_client():
    settings = Settings(database_url_override="sqlite+aiosqlite:///:memory:")
    db = Database(settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    cache = RedisCache.__new__(RedisCache)
    cache._settings = settings
    cache._client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    cache._pool = None
    reg = EventRegistry()
    register_default_handlers(reg)
    state = AppState(
        settings=settings, db=db, cache=cache, providers=build_registry(), events=EventBus(reg)
    )
    app = create_app(settings)
    app.state.xlink = state
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://audit")
    return client, db, cache


async def worker(client, method, path, n, results, errors, timeouts, payload_fn=None, headers=None):
    for _ in range(n):
        body = payload_fn() if payload_fn else None
        t0 = time.perf_counter()
        try:
            r = await client.request(method, path, json=body, headers=headers, timeout=10.0)
            dt = (time.perf_counter() - t0) * 1000
            results.append(dt)
            if r.status_code >= 500:
                errors.append(r.status_code)
        except asyncio.TimeoutError:
            timeouts.append(1)
        except Exception:
            errors.append(-1)


async def scenario(client, name, method, path, total, concurrency, payload_fn=None, headers=None):
    results, errors, timeouts = [], [], []
    per = max(1, total // concurrency)
    rss0 = PROC.memory_info().rss / 1024 / 1024
    cpu0 = PROC.cpu_times()
    t0 = time.perf_counter()
    tasks = [
        asyncio.create_task(
            worker(client, method, path, per, results, errors, timeouts, payload_fn, headers)
        )
        for _ in range(concurrency)
    ]
    await asyncio.gather(*tasks)
    wall = time.perf_counter() - t0
    cpu1 = PROC.cpu_times()
    rss1 = PROC.memory_info().rss / 1024 / 1024
    done = len(results)
    rps = done / wall if wall else 0
    err_rate = (len(errors) + len(timeouts)) / max(1, done + len(errors) + len(timeouts)) * 100
    cpu_used = (cpu1.user - cpu0.user) + (cpu1.system - cpu0.system)
    print(
        f"  {name:30s} n={done:5d} conc={concurrency:3d} "
        f"RPS={rps:8.1f} p50={pct(results, 0.5):6.1f} p95={pct(results, 0.95):6.1f} "
        f"p99={pct(results, 0.99):6.1f} err%={err_rate:4.1f} to={len(timeouts):3d} "
        f"cpu={cpu_used:4.1f}s rss={rss0:.0f}->{rss1:.0f}MB"
    )
    return {"rps": rps, "p99": pct(results, 0.99), "err": err_rate}


_ctr = [0]


def reg_payload():
    _ctr[0] += 1
    i = _ctr[0]
    return {
        "email": f"load{i}@audit.io",
        "username": f"load{i}",
        "password": "Str0ng-Passw0rd-123!",
        "full_name": "Load Test",
    }


async def main():
    client, db, cache = await build_client()
    print("=" * 78)
    print("LOCAL LOAD TEST — in-process ASGI, SQLite :memory:, fakeredis")
    print("=" * 78)

    await scenario(client, "health /live (warmup)", "GET", "/api/v1/health/live", 200, 10)

    print("\n[A] HEALTH — cheap endpoint, rising concurrency:")
    for conc in (10, 50, 100, 200):
        await scenario(client, f"health /live", "GET", "/api/v1/health/live", 2000, conc)

    print("\n[B] AUTH register — Argon2 hash on bounded thread pool:")
    for conc in (10, 25, 50):
        await scenario(
            client,
            "auth /register",
            "POST",
            "/api/v1/auth/register",
            200,
            conc,
            payload_fn=reg_payload,
        )

    print("\n[C] AUTH login — Argon2 verify (reuse one seeded user):")
    seed = {
        "email": "fixed@audit.io",
        "username": "fixeduser",
        "password": "Str0ng-Passw0rd-123!",
        "full_name": "x",
    }
    await client.post("/api/v1/auth/register", json=seed)
    login = {"username": "fixeduser", "password": "Str0ng-Passw0rd-123!"}
    for conc in (10, 25, 50):
        await scenario(
            client,
            "auth /login",
            "POST",
            "/api/v1/auth/login",
            200,
            conc,
            payload_fn=lambda: dict(login),
        )

    print("\n[D] READY (DB+Redis ping each request):")
    for conc in (10, 50, 100):
        await scenario(client, "health /ready", "GET", "/api/v1/health/ready", 1000, conc)

    await client.aclose()
    await cache.client.aclose()
    await db.dispose()
    print(f"\nFINAL RSS={PROC.memory_info().rss / 1024 / 1024:.0f}MB")


if __name__ == "__main__":
    asyncio.run(main())
