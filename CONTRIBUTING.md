# Contributing to XLink

Thanks for your interest in improving XLink. This guide covers the local setup,
the checks a change must pass, and how to open a good pull request.

## Project layout

| Path | What it is |
| ---- | ---------- |
| `app/` | FastAPI backend — `api → services → repositories → db`; `domain` and `schemas` stay dependency-free |
| `web/` | Next.js admin console |
| `node-agent/` | Pull-based Python agent that applies core configs on each node |
| `alembic/` | Database migrations (single head) |

## Local setup

Requirements: Python **3.13+**, [uv](https://docs.astral.sh/uv/), Node.js, Docker.

```bash
# Backend deps
uv sync --extra dev

# Datastores
docker compose up -d postgres redis

# Migrate + run the API
uv run alembic upgrade head
uv run ./scripts/dev.sh

# Web console (separate terminal)
cd web && npm install && npm run dev
```

## Before you push

All of these must pass:

```bash
ruff check .          # lint
ruff format --check . # formatting
mypy app              # type check (backend)
uv run pytest         # backend tests

cd web && ./node_modules/.bin/tsc --noEmit   # type check (web)
```

> **Never run `next build`** during development — the dev server is always
> running and a parallel build corrupts `.next`. Use `tsc --noEmit` to type-check
> the web app.

## Database changes

Any change to a model in `app/domain/` needs a matching Alembic migration:

```bash
uv run alembic revision -m "short description"   # then edit the generated file
uv run alembic upgrade head
```

Keep the migration chain to a **single head** — rebase onto the current head
rather than branching it.

## Pull requests

- Branch off `main`; keep each PR focused on one change.
- Write a clear title and description: what changed and why. Link any related
  issue.
- Match the style of the surrounding code — naming, comment density, and idiom.
- Include tests for new behavior and bug fixes.
- Make sure every check above passes locally before requesting review.

## Security issues

Do **not** open a public issue or PR for a vulnerability — follow
[SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the
[Apache-2.0](LICENSE) license that covers the project.
