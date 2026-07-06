# XLink

Multi-node VPN management panel. FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL 16
+ Redis backend, Next.js 15 admin console, and a pull-based node agent. Scales to
50,000+ users and hundreds of nodes.

Supports xray, sing-box, hysteria, and wireguard cores (vless / vmess / trojan /
shadowsocks / hysteria2 / tuic / wireguard), 15 subscription formats with
User-Agent routing, per-user data/expiry/device limits, multi-node load-balancing
and failover, drift detection + self-healing, traffic accounting, Prometheus
metrics, audit log, and backups.

## Architecture

Clean Architecture with a strict dependency direction
(`api → services → repositories → db`; `domain` and `schemas` are dependency-free):

```
app/
├── api/            # HTTP layer: routers, request wiring (thin)
├── core/           # config, logging, security, exceptions, lifespan
├── db/             # async engine/session, declarative base, Redis client
├── domain/         # ORM models / domain entities (no business logic deps)
├── repositories/   # data access (Repository Pattern), N+1-safe queries
├── services/       # business logic (Service Layer), transaction boundaries
├── schemas/        # Pydantic v2 DTOs (request/response contracts)
├── middleware/     # request-id, structured access logs, security headers
├── dependencies/   # FastAPI DI providers (no global state)
└── tests/          # pytest-asyncio test suite
```

## Quick start

```bash
cp .env.example .env
# set XLINK_JWT_SECRET_KEY (openssl rand -hex 32), XLINK_POSTGRES_PASSWORD,
# and XLINK_ADMIN_USERNAME / XLINK_ADMIN_PASSWORD (the panel creates this admin
# on first boot — log in with it, then you can drop the password line).

make install            # generates the JWT secret, builds, and starts everything
```

Then open the panel at **http://localhost:3000** and log in with the
`XLINK_ADMIN_*` credentials from `.env`.

The stack is `web` (admin UI :3000) → `api` (:8000) → `migrate` → `postgres` +
`redis`. `make install` runs them in order; the api waits for migrations to
finish before starting.

```bash
# everyday commands
make up / make down / make deploy / make logs
make cli c='user list'          # or: ./xlink user list
./xlink admin reset-password -u admin -p NEWPASS   # locked out? recover here
```

Local dev (api outside Docker against compose infra):

```bash
docker compose up -d postgres redis
pip install -e ".[dev]"
alembic upgrade head
./scripts/dev.sh
cd web && npm install && npm run dev   # UI on :3000
```

API docs: http://localhost:8000/docs · OpenAPI: `/api/v1/openapi.json`

## Key endpoints

| Method | Path                         | Description                       |
|--------|------------------------------|-----------------------------------|
| GET    | `/api/v1/health/live`        | Liveness probe                    |
| GET    | `/api/v1/health/ready`       | Readiness (DB + Redis)            |
| POST   | `/api/v1/auth/register`      | Create account                    |
| POST   | `/api/v1/auth/login`         | Obtain access + refresh tokens    |
| POST   | `/api/v1/auth/refresh`       | Rotate refresh token              |
| POST   | `/api/v1/auth/logout`        | Revoke refresh token              |
| GET    | `/api/v1/users/me`           | Current user profile              |
| GET    | `/api/v1/users`              | User list (admin) — keyset by default |
| GET    | `/api/v1/users/cursor`       | User list (admin) — explicit keyset   |

### User listing pagination

`GET /api/v1/users` defaults to **keyset (cursor) pagination** and does not run
a `COUNT(*)`. It returns `{ items, next_cursor, size }`; pass the returned
`next_cursor` (and optional `size`, `role`, `is_active`) to fetch the next page.

Offset pagination is opt-in: pass an explicit `page` query parameter to get the
legacy `{ items, meta: { page, size, total, pages } }` shape (this runs a
`COUNT(*)` and is intended for small/admin datasets only).

## Tooling

```bash
ruff check . && ruff format --check .   # lint + format
mypy app                                # type check
pytest                                  # tests (uses SQLite + fakeredis)
alembic revision --autogenerate -m "…"  # new migration
```

## Production notes

- Run DB migrations as a separate step (the compose `migrate` service / a k8s
  Job), never from the API container, so replicas don't race on `upgrade`.
- Set `XLINK_LOG_JSON=true` and a strong `XLINK_JWT_SECRET_KEY` in production.
- The app is stateless: scale by adding replicas behind a load balancer.
  All shared state lives in Postgres and Redis.
