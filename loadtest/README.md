# XLink Load Test

Proves the **10k-user / 50-node** scale claim with a realistic, weighted traffic
mix using [Locust](https://locust.io).

## What it exercises

The user classes mirror real production load, weighted by how often each actor
hits the API:

| Class | Weight | Simulates | Hot paths |
|---|---|---|---|
| `SubscriberUser` | 8 | VPN clients pulling their config | `GET /sub/{token}` with `If-None-Match` (ETag/304 cache) |
| `NodeAgent` | 2 | node agents polling + reporting | `GET /agent/nodes/{id}/config` (known_version → 304), `POST .../traffic` |
| `AdminUser` | 1 | panel operators | login, list users, dashboard summary, create/delete user |

The subscriber path is weighted highest on purpose — in production it is by far
the highest-QPS endpoint (every client re-fetches on an interval), and it is the
one the global-epoch + per-subject-revision cache and single-flight lock were
built for. The `If-None-Match` flow verifies the 304 fast path under load.

## Setup

```bash
pip install locust           # or: .venv/bin/pip install locust
```

## 1. Seed subscribers

```bash
SEED_COUNT=10000 .venv/bin/python loadtest/seed.py
```

Creates N `USER` rows and writes their signed subscription tokens to
`loadtest/.sub_tokens`. Run against the SAME database the API under test uses
(set the usual `XLINK_*` DB env vars).

## 2. Run

```bash
XLINK_ADMIN_PASSWORD='<admin-pass>' \
XLINK_NODE_ID='<a-real-node-id>' \
XLINK_NODE_TOKEN='<that-node-agent-token>' \
loadtest/run.sh http://127.0.0.1:8000 10000 200 10m
```

Args: `<host> <users> <spawn-rate> <duration>`. Env vars are optional — any
actor whose credentials are missing becomes a no-op (a warning prints at start),
so you can load-test just the subscriber path with only the seed step.

Outputs `loadtest/report.html` + `loadtest/report_*.csv`.

## Reading results — pass/fail bar

For the 10k/50 claim to hold on the reference box, target:

- **Sub fetch p95 < 150 ms**, failure rate ~0% (mostly 304s after warm-up).
- **Agent config p95 < 200 ms**, dominated by 304s once `known_version` matches.
- **No 5xx** under sustained load; DB pool never exhausted (watch
  `QueuePool limit ... overflow` in API logs — if it appears, raise
  `XLINK_DB_POOL_SIZE` / add the read replica).
- **Postgres CPU and connection count stable** (not climbing to the cap).

If sub-fetch p95 climbs or 5xx appears, the usual levers are: enable the read
replica (`XLINK_POSTGRES_REPLICA_HOST`), raise gunicorn workers, and confirm
Redis is the cache backend (not a cold cache every request).

## Notes

- Seeded users have no assignments, so their feed is small; to test feed-render
  cost, assign some seeded users to a profile first, or point `XLINK_SUB_TOKENS`
  at real provisioned users.
- This is a black-box HTTP test — run it against a production-like deploy
  (gunicorn multi-worker + Postgres + Redis), not the dev autoreload server, or
  the numbers are meaningless.
