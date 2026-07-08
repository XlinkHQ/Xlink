# Contributing to XLink

Thank you for taking the time to contribute. This document explains how the
project is organized, how to set up a local environment, the quality bar every
change must meet, and how to get a pull request reviewed and merged. Reading it
end-to-end once will save a round of review comments later.

By participating you agree to keep interactions respectful and professional, and
that your contributions are licensed under the project's [Apache-2.0](LICENSE)
license.

## Table of contents

- [Ways to contribute](#ways-to-contribute)
- [Project layout](#project-layout)
- [Local setup](#local-setup)
- [Running the stack](#running-the-stack)
- [The quality bar](#the-quality-bar)
- [Coding standards](#coding-standards)
- [Database migrations](#database-migrations)
- [Tests](#tests)
- [Commit messages](#commit-messages)
- [Pull requests](#pull-requests)
- [Reporting bugs](#reporting-bugs)
- [Security issues](#security-issues)

## Ways to contribute

- **Report a bug** using the issue form — include steps to reproduce, the
  affected component, and the version/commit.
- **Propose a feature** using the feature-request form — describe the problem
  first, then the proposed solution.
- **Improve documentation** — corrections and clarifications are always welcome
  and are a great first contribution.
- **Fix a bug or build a feature** — for anything non-trivial, open an issue
  first so the approach can be agreed before you invest time.

## Project layout

| Path | What it is |
| ---- | ---------- |
| `app/` | FastAPI backend. Strict layering: `api → services → repositories → db`; `domain` and `schemas` are dependency-free. |
| `app/api/v1/routers/` | HTTP endpoints, one module per domain (users, nodes, profiles, traffic, subscriptions, …). |
| `app/services/` | Business logic. Routers call services; services call repositories. |
| `app/repositories/` | Data access. The only layer that talks to the database. |
| `app/subscription/` | Subscription feed generator, per-format renderers, and the token layer. |
| `app/agent/` | Node-facing plane: config sync, command lease/execute, traffic ingest, IP limits. |
| `app/providers/` | Per-core config builders (xray, sing-box, hysteria, wireguard). |
| `web/` | Next.js 15 admin console (TypeScript). |
| `node-agent/` | The pull-based Python agent that runs on each node. |
| `alembic/` | Database migrations — a single linear head. |
| `scripts/` | Installer and developer helpers. |

Respect the layering: a router must not touch the database directly, and
`domain`/`schemas` must not import from `services`/`repositories`. Reviews will
flag layering violations.

## Local setup

Requirements:

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** for Python dependency management
- **Node.js** (for the web console)
- **Docker** with Compose (for Postgres and Redis)

Install dependencies:

```bash
# Backend, including the dev extras (ruff, mypy, pytest)
uv sync --extra dev

# Web console
cd web && npm install && cd ..
```

## Running the stack

```bash
# 1. Datastores
docker compose up -d postgres redis

# 2. Apply migrations
uv run alembic upgrade head

# 3. Run the API (hot-reload)
uv run ./scripts/dev.sh

# 4. Run the admin console (separate terminal)
cd web && npm run dev
```

The API is then at `http://localhost:8000` (docs at `/docs`) and the console at
`http://localhost:3000`.

> **Never run `next build` locally.** The dev server is expected to be running,
> and a parallel production build corrupts `.next`. To verify the web app
> type-checks, use `tsc --noEmit` (below).

## The quality bar

Every change must pass all of the following **before** you request review. CI runs
the same checks; running them locally first keeps the loop fast.

```bash
# Backend
ruff check .            # lint (E, F, I, N, UP, B, C4, SIM, ASYNC, RUF)
ruff format --check .   # formatting (line length 100)
mypy app                # static type checking
uv run pytest           # test suite

# Web (only if web/ changed)
cd web && ./node_modules/.bin/tsc --noEmit
```

If a check is failing for a reason unrelated to your change, say so in the PR
rather than disabling it.

## Coding standards

- **Match the surrounding code.** New code should read like the code next to it —
  same naming, comment density, and idioms. Consistency beats personal preference.
- **Line length is 100.** Ruff enforces it and also handles import sorting
  (first-party = `app`), so let the tools format rather than hand-aligning.
- **Type everything.** `mypy app` runs in the standard configuration; annotate new
  functions and avoid `Any` where a concrete type is known.
- **Async all the way down** in the backend — use the async SQLAlchemy session and
  `await` I/O; don't block the event loop.
- **Comment the "why", not the "what".** Explain non-obvious decisions, edge
  cases, and invariants; skip comments that merely restate the code.
- **No secrets in code, tests, fixtures, or logs.** Never commit real tokens,
  passwords, keys, or server IPs.
- **Web**: TypeScript, reuse the existing component and design system (`.warp-*`
  classes); do not introduce new styling patterns for something already solved.

## Database migrations

Any change to a model under `app/domain/` needs a matching Alembic migration in
the same PR:

```bash
uv run alembic revision -m "short, imperative description"
# edit the generated file: implement upgrade() AND downgrade()
uv run alembic upgrade head    # verify it applies
uv run alembic downgrade -1    # verify it reverses, then upgrade again
```

Keep the chain to a **single head** — if `main` advanced while you worked, rebase
your migration onto the current head rather than creating a branch. Include a
sensible `server_default` when adding a non-nullable column to a populated table.

## Tests

- Tests live next to the code they cover (e.g. `app/subscription/tests/`,
  `app/agent/tests/`) as well as in the top-level `app/tests/`.
- Add tests for **new behavior** and a **regression test** for every bug fix — a
  bug fix without a test that would have caught it is incomplete.
- Run the whole suite with `uv run pytest`; scope while iterating with
  `uv run pytest app/subscription -q` or `-k <expr>`.
- The PostgreSQL-only concurrency tests are skipped unless
  `XLINK_TEST_DATABASE_URL` points at a real Postgres DSN — the default SQLite run
  covers everything else.

## Commit messages

Use short, imperative, [Conventional Commits](https://www.conventionalcommits.org/)
style prefixes so history stays scannable:

```
fix(subscriptions): render shadowtls in sing-box feeds
feat(nodes): per-core restart from the console
docs: expand deployment guide
chore: drop redundant deploy wrapper
```

Explain the *why* in the body when it isn't obvious from the subject. Keep each
commit focused; don't mix unrelated changes.

## Pull requests

- Branch off `main`, one logical change per PR.
- Fill in the PR template: what changed, why, and the linked issue.
- Ensure every check in [The quality bar](#the-quality-bar) passes locally.
- Include tests, and a migration if a model changed.
- Update user-facing docs and `CHANGELOG.md` (`Unreleased` section) when behavior
  changes.
- Keep the diff reviewable — avoid drive-by reformatting of untouched code.

A maintainer will review, possibly request changes, and merge once it's green and
approved.

## Reporting bugs

Open an issue with the bug-report form. A good report has: what you expected vs.
what happened, exact steps to reproduce, the affected component, the version or
commit, and relevant logs (with secrets and IPs redacted).

## Security issues

**Do not open a public issue or pull request for a security vulnerability.**
Report it privately through GitHub's
[private advisory](https://github.com/Theok09/Xlink/security/advisories/new) form.
See [SECURITY.md](SECURITY.md) for the full policy.
