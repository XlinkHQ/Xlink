# Contributing to XLink

Thanks for your interest in improving XLink. This guide covers everything you
need to get set up, make a change, and open a pull request.

## 🚀 Quick start

```bash
git clone https://github.com/XlinkHQ/Xlink.git
cd Xlink
uv sync --extra dev
docker compose up -d postgres redis
uv run alembic upgrade head
uv run ./scripts/dev.sh
```

You need Python 3.13+, [uv](https://docs.astral.sh/uv/), Node.js, and Docker.
The web console runs separately:

```bash
cd web && npm install && npm run dev
```

> [!NOTE]
> The API is served at `http://localhost:8000` (docs at `/docs`) and the console
> at `http://localhost:3000`.

## 📁 Project layout

| Path | What it is |
| ---- | ---------- |
| `app/` | FastAPI backend, layered `api → services → repositories → db` |
| `app/api/v1/routers/` | HTTP endpoints, one module per domain |
| `app/subscription/` | Feed generator, per-format renderers, token layer |
| `app/agent/` | Node-facing plane: config sync, commands, traffic ingest |
| `app/traffic/`, `app/failover/` | Traffic accounting + rollups, node failover |
| `web/` | Next.js admin console |
| `node-agent/` | The pull-based agent that runs on each node |
| `sdk/python/` | Official Python SDK |
| `alembic/` | Database migrations (single head) |

## 🤝 How to contribute

1. **Open an issue first** for anything non-trivial, so the approach can be
   agreed before you write code.
2. **Fork and branch** from `main`: `git checkout -b fix/short-description`.
3. **Make your change**, with tests.
4. **Run the checks** below until they pass.
5. **Open a pull request** against `main` using the template. Keep it focused —
   one change per pull request gets reviewed fastest.

## ✅ Before you push

```bash
ruff check . && ruff format --check .          # lint and formatting
mypy app                                       # backend types
uv run pytest                                  # backend tests
cd web && ./node_modules/.bin/tsc --noEmit     # web types
```

> [!IMPORTANT]
> Do not run `next build` during development. The dev server is expected to be
> running, and a parallel production build corrupts `.next`. Use `tsc --noEmit`
> to type-check the web app.

## 📐 Coding standards

- **Async all the way down** in the backend — use the async SQLAlchemy session
  and `await` I/O; never block the event loop.
- **Match the surrounding code** — same naming, structure, and idioms. The
  layering (`api → services → repositories → db`, `domain`/`schemas` dependency-
  free) is enforced in review.
- **Comment the why, not the what.** Explain a decision, an edge case, or an
  invariant; do not restate the code.
- **Type everything.** `mypy app` runs in its standard config; avoid `Any` where
  a concrete type is known.
- **Tests are required.** Every bug fix needs a regression test that fails
  without the fix; every feature needs coverage.
- **A model change needs a migration** in the same pull request, kept to a single
  Alembic head with a working `downgrade()`.
- **On the web side**, reuse the existing components and the `.warp-*` design
  system rather than inventing a new pattern.

## 📝 Commit messages

Use the imperative mood and a
[Conventional Commits](https://www.conventionalcommits.org/) prefix; keep the
subject under 72 characters and put the reasoning in the body.

```
fix(subscriptions): render shadowtls in sing-box feeds

Fixes #12.
```

> [!WARNING]
> Never commit a secret, token, key, server IP, or `.env` file. If you leak a
> secret, rotate it immediately.

## 🔒 Security issues

Do not open a public issue for a vulnerability. Follow the
[security policy](SECURITY.md) to report it privately.

## ⚖️ License

By contributing, you agree that your contributions are licensed under the
[Apache License 2.0](LICENSE).
