# Contributing to XLink

Glad you're here. This is the practical guide to working on XLink — how the code
is laid out, how to get it running locally, what has to pass before a change can
merge, and how the review works. It's worth reading once; it'll save you a
round-trip in review.

Two ground rules up front: keep things civil, and know that anything you
contribute goes in under the project's [Apache-2.0](LICENSE) license.

## What's worth contributing

Bug reports are always useful — the issue form asks for steps to reproduce, which
part broke, and the version or commit, because those three things are what make a
report actually fixable. Feature ideas are welcome too; describe the problem
you're hitting before the solution you have in mind, since the problem often has a
simpler fix than the feature. Documentation fixes are genuinely appreciated and
make a great first PR. And if you want to fix a bug or build something bigger,
open an issue first for anything non-trivial — it's no fun to write a feature and
then find out in review it should have worked a different way.

## How the code is laid out

| Path | What it is |
| ---- | ---------- |
| `app/` | FastAPI backend. Layered: `api → services → repositories → db`; `domain` and `schemas` stay dependency-free. |
| `app/api/v1/routers/` | HTTP endpoints, one module per area (users, nodes, profiles, traffic, subscriptions, …). |
| `app/services/` | The business logic. Routers call services; services call repositories. |
| `app/repositories/` | Data access — the only layer that touches the database. |
| `app/subscription/` | Feed generator, the per-format renderers, and the token layer. |
| `app/agent/` | Everything node-facing: config sync, command lease/execute, traffic ingest, IP limits. |
| `app/providers/` | Per-core config builders (xray, sing-box, hysteria, wireguard). |
| `web/` | The Next.js 15 console (TypeScript). |
| `node-agent/` | The agent that runs on each node. |
| `alembic/` | Database migrations — one linear head. |
| `scripts/` | Installer and dev helpers. |

The layering isn't decorative. A router shouldn't reach into the database, and
`domain`/`schemas` shouldn't import from `services` or `repositories`. It keeps the
code testable and the dependencies pointing one direction, and review will push
back on changes that cross those lines.

## Getting it running

You'll need Python 3.13+, [uv](https://docs.astral.sh/uv/) for the Python side,
Node.js for the console, and Docker for Postgres and Redis.

Install the dependencies:

```bash
uv sync --extra dev          # backend, with ruff/mypy/pytest
cd web && npm install && cd ..
```

Then bring up the stack:

```bash
docker compose up -d postgres redis    # datastores
uv run alembic upgrade head            # migrations
uv run ./scripts/dev.sh                # the API, with hot reload

cd web && npm run dev                  # the console, in another terminal
```

The API lands on `http://localhost:8000` (docs at `/docs`), the console on
`http://localhost:3000`.

One warning that trips people up: **don't run `next build` locally.** The dev
server is meant to be running, and a production build alongside it corrupts
`.next`. When you want to check the web app compiles, use `tsc --noEmit` — see
below.

## What has to pass

Run these before you ask for review. CI runs the exact same set, so getting them
green locally first just saves you the round-trip:

```bash
ruff check .            # lint (E, F, I, N, UP, B, C4, SIM, ASYNC, RUF)
ruff format --check .   # formatting — line length is 100
mypy app                # types
uv run pytest           # the backend suite

cd web && ./node_modules/.bin/tsc --noEmit   # web types, if you touched web/
```

If one of these is red for a reason that has nothing to do with your change, don't
paper over it — call it out in the PR instead.

## Writing code that fits

The single most useful habit is to make new code read like the code already
around it — same names, same comment density, same idioms. Consistency is worth
more here than any individual preference.

A few specifics that come up in review:

- Ruff owns formatting and import order (first-party is `app`), so let it format
  rather than aligning things by hand. Line length is 100.
- Type your code. `mypy app` runs in its normal config; annotate new functions and
  don't reach for `Any` when the real type is known.
- The backend is async top to bottom — use the async SQLAlchemy session and
  `await` your I/O, don't block the event loop.
- Comment the *why*, not the *what*. A comment that explains a non-obvious
  decision or an edge case earns its place; one that restates the line above it
  doesn't.
- No secrets anywhere — not in code, tests, fixtures, or logs. That includes real
  tokens, passwords, keys, and server IPs.
- On the web side, reuse the existing components and the `.warp-*` design system
  rather than inventing a new pattern for something already solved.

## Database changes

If you change a model under `app/domain/`, the migration goes in the same PR:

```bash
uv run alembic revision -m "short, imperative description"
# then edit the generated file — write both upgrade() and downgrade()
uv run alembic upgrade head     # check it applies
uv run alembic downgrade -1     # check it reverses, then upgrade again
```

Keep the chain to a single head; if `main` moved while you were working, rebase
your migration onto the new head instead of branching it. And when you add a
non-nullable column to a table that already has rows, give it a sensible
`server_default` so the migration doesn't fail on real data.

## Tests

Tests sit next to the code they cover — `app/subscription/tests/`,
`app/agent/tests/`, and so on — plus the broader ones in `app/tests/`. New
behavior needs tests, and every bug fix needs a regression test; a fix without a
test that would have caught the bug isn't really finished. Run the whole suite
with `uv run pytest`, or narrow it while you iterate with `uv run pytest
app/subscription -q` or `-k <expr>`. The PostgreSQL-only concurrency tests skip
themselves unless `XLINK_TEST_DATABASE_URL` points at a real Postgres — the
default SQLite run covers everything else.

## Commits and pull requests

Keep commit subjects short and imperative, with a
[Conventional Commits](https://www.conventionalcommits.org/) prefix so the history
stays easy to scan:

```
fix(subscriptions): render shadowtls in sing-box feeds
feat(nodes): per-core restart from the console
docs: expand the deployment guide
chore: drop the redundant deploy wrapper
```

Put the *why* in the body when the subject doesn't make it obvious, and keep each
commit to one thing.

For the PR itself: branch off `main`, one logical change per PR, and fill in the
template (what changed, why, the linked issue). Make sure everything under
[what has to pass](#what-has-to-pass) is green, bring the tests and any migration
along with the code, and update the docs and the `Unreleased` section of
[CHANGELOG.md](CHANGELOG.md) if behavior changed. Try not to reformat untouched
code in the same diff — it makes the real change harder to see. A maintainer will
review, maybe ask for changes, and merge once it's green and approved.

## Security

Don't use a public issue or PR for a security problem. Report it privately through
GitHub's
[advisory form](https://github.com/Theok09/Xlink/security/advisories/new);
[SECURITY.md](SECURITY.md) has the full policy.
