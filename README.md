# XLink

Production-grade async backend foundation built with FastAPI, SQLAlchemy 2.0
(async), PostgreSQL 16, and Redis. Designed to scale horizontally to 50,000+
users and hundreds of nodes.

> Scope of this foundation: authentication (Argon2 + JWT access/refresh),
> user management, health checks, caching, structured logging, and the full
> Clean Architecture skeleton. **Xray, subscriptions, and node sync are
> intentionally out of scope** and are not implemented here.

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
./scripts/gen_secret.sh   # paste output into XLINK_JWT_SECRET_KEY

# Full stack (api + migrations + postgres + redis)
docker compose up --build

# Or run the API locally against compose infra
docker compose up -d postgres redis
pip install -e ".[dev]"
alembic upgrade head
./scripts/dev.sh
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
