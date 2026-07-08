<div align="center">

<img src="docs/assets/logo.png" alt="XLink" width="420" />

### Multi-node VPN management panel for xray, sing-box, hysteria, and WireGuard

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](pyproject.toml)
[![Next.js 15](https://img.shields.io/badge/Next.js-15-black.svg)](web/package.json)

</div>

---

XLink is a panel for running your own VPN service across more than one server. You
add your nodes, create users, and hand each user a single subscription link — the
panel takes care of pushing the right config to every node, keeping traffic
counted per user, and moving people off a node when it goes down.

It grew out of the usual frustration with single-server panels: once you have two
or three locations, you end up copying configs by hand, and you never really know
how much each user has actually used — especially on WireGuard, where most panels
just give up on per-user accounting. XLink treats a user as a real account with a
data cap, an expiry, and a device limit, and it measures traffic on every core,
WireGuard included.

The important design choice is that **the panel never connects into a node**. Each
node runs a small agent that reaches out to the panel, pulls the config it's
supposed to have, applies it locally, and reports back. So a node only needs to be
able to talk *out* to the panel's API — you don't have to open it up or trust the
panel with SSH keys.

## Table of contents

- [What you get](#what-you-get)
- [How it fits together](#how-it-fits-together)
- [Getting started](#getting-started)
- [Running the panel day to day](#running-the-panel-day-to-day)
- [Adding a node](#adding-a-node)
- [Configuration](#configuration)
- [Working on XLink](#working-on-xlink)
- [Where things live](#where-things-live)
- [Documentation](#documentation)
- [Security](#security)
- [License](#license)

## What you get

**The cores you'd expect.** xray, sing-box, hysteria, and WireGuard, chosen per
profile. Between them that covers vless, vmess, trojan, shadowsocks, shadowtls,
hysteria2, tuic, naive, socks, and wireguard, each with the transport and TLS
options its core actually supports.

**Users that behave like accounts.** Every user has a data cap, an expiry (a fixed
date, or "start counting on first use"), and an optional device limit that can key
off HWID. Usage can reset on a schedule. Each user gets one subscription token —
signed, scoped to that user, and revocable — and the panel renders it into
whatever the client asks for: plain list, base64, sing-box JSON, Clash/Mihomo
YAML, xray JSON, or a single protocol URI, picking the format from the client's
user-agent.

**A fleet, not one box.** Run as many nodes as you like, with load-balancing and
automatic failover between them. The agent delivers traffic through a write-ahead
log so a dropped connection never double-counts or loses usage, reports health
every cycle, and can install, update, or restart individual cores on command.
Certificates are handled with ACME through the bundled edge proxy, so HTTPS is
automatic once you point a domain at the panel.

**Room for resellers and automation.** Access control has real roles: sudo admins
who see everything, and scoped reseller-admins who only see the users, groups, and
profiles that belong to them. There's an audit log, GitOps config sync, a
scheduler for recurring jobs, notifications, retention settings, database backups,
and Prometheus-style metrics. Everything the console does is also available through
API keys and a CLI, so you can script it.

## How it fits together

```
                    ┌─────────────────────── Panel server ───────────────────────┐
                    │ web (:3000)  ──▶  api (:8000)  ──▶  postgres               │
                    │                       └──▶  redis                          │
                    │                  └──▶  migrate (one-shot)                  │
                    └────────────────────────────────────────────────────────────┘
                                                   │  ▲
                                node dials out ──▶ │  │ ◀── reports traffic
                                                   ▼  │   (HTTPS)
                    ┌─────────────────────── Node servers ───────────────────────┐
                    │ xlink-agent  ──▶  xray / sing-box / hysteria / wireguard   │
                    └────────────────────────────────────────────────────────────┘
```

The panel is a FastAPI backend with a Next.js console in front of it, backed by
PostgreSQL and Redis. The backend is layered on purpose — `api → services →
repositories → db`, with the domain models and schemas kept free of any dependency
on the layers above — so it stays testable and the boundaries don't blur over
time. If you'd rather read the API than the code, Swagger UI is at
`http://<panel>:8000/docs` outside production.

## Getting started

On a fresh Linux server, as root:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Theok09/Xlink/main/scripts/install.sh)
```

That one command installs Docker if it isn't already there, clones the repo to
`/opt/xlink`, generates a fresh set of secrets, pulls (or builds) the images, runs
the database migrations, brings the whole stack up, and prints the panel URL along
with a one-time admin password. Run it again whenever you want to update — it
updates in place and leaves your `.env` alone. Add `--build` if you'd rather build
the images on the box than pull them.

If you want to see each step yourself instead of trusting a one-liner,
[DEPLOY.md](DEPLOY.md) walks through it manually.

## Running the panel day to day

From the install directory, `xlink` wraps the things you'll do most:

```bash
xlink up | down | restart | status | logs
xlink update                 # pull latest, migrate, restart
xlink backup                 # snapshot the database
xlink edit                   # edit .env, then restart
```

Anything an admin can do is also on the CLI (it runs inside the api container):

```bash
xlink admin reset-password -u admin -p NEWPASS   # get back in if you're locked out
xlink admin create -u reseller --no-sudo         # a scoped reseller-admin
xlink user list [--status S] [--owner ADMIN]
xlink user create -u alice --limit 50 --expire 2026-12-31
xlink user show -u alice                          # details + subscription link
xlink node create -n edge-1 --host 203.0.113.10 --port 443
xlink node token edge-1                            # agent token, shown once
```

`xlink help` lists everything.

## Adding a node

Adding a location is two steps. First, in the console under **Nodes**, add the
node with its public host and core port and provision an agent token — you'll get
a node id and a token. Then, on the node server, run the agent installer with
those values:

```bash
curl -fsSL https://<panel-host>:8000/agent/install.sh \
  | sudo -E bash -s https://<panel-host> <node-id> <agent-token>
```

By default it installs every core; narrow it with `--cores=xray,wireguard` if the
node only needs some. Watch it come up with `journalctl -u xlink-agent -f` — once
you see `pulled config` the agent is talking to the panel, and the node flips to
**active** in the console within about half a minute.

## Configuration

Everything is configured through environment variables, and the installer writes a
complete `.env` with secrets already generated, so you normally don't touch it. The
full list is in [.env.example](.env.example); these are the ones people actually
change:

| Variable | What it does | Default |
| -------- | ------------ | ------- |
| `XLINK_DOMAIN` | Set a domain to turn on the ACME/HTTPS edge proxy | unset — plain ports |
| `XLINK_ACME_EMAIL` | Contact address for Let's Encrypt | — |
| `XLINK_PORT` | API port — this is what nodes connect to | `8000` |
| `XLINK_PUBLIC_IP` | Override the server IP shown on the dashboard (auto-detected otherwise) | auto |
| `XLINK_JWT_SECRET_KEY` | Signs auth and subscription tokens | generated |
| `XLINK_LOG_JSON` | Structured JSON logs — worth turning on in production | `false` |

The secrets only ever live in `.env` on the panel server, and that file is
git-ignored. Don't commit it.

## Working on XLink

You'll need Python 3.13+, [uv](https://docs.astral.sh/uv/), Node.js, and Docker.

```bash
uv sync --extra dev                    # backend deps
docker compose up -d postgres redis    # datastores
uv run alembic upgrade head            # migrate
uv run ./scripts/dev.sh                # run the API

cd web && npm install && npm run dev   # the console, in another terminal
```

Before you send a pull request, make sure the checks pass — the same ones CI runs:

```bash
ruff check . && ruff format --check .   # lint + formatting
mypy app                                # backend types
uv run pytest                           # backend tests
cd web && ./node_modules/.bin/tsc --noEmit   # web types
```

One thing to know: **don't run `next build` while developing.** The dev server is
always up, and a build running next to it corrupts `.next`. Use `tsc --noEmit` to
check the web app instead. [CONTRIBUTING.md](CONTRIBUTING.md) has the rest.

## Where things live

| Path | What's there |
| ---- | ------------ |
| `app/` | The FastAPI backend (`api → services → repositories → db`) |
| `app/api/v1/routers/` | HTTP endpoints, one file per area — users, nodes, profiles, traffic, and so on |
| `app/subscription/` | Subscription feed generator, the per-format renderers, and the token layer |
| `app/agent/` | Everything node-facing: config sync, commands, traffic ingest, IP limits |
| `web/` | The Next.js console |
| `node-agent/` | The agent that runs on each node |
| `alembic/` | Database migrations (kept to a single head) |
| `scripts/` | The installer and dev helpers |
| `xlink`, `xlink.sh` | The runtime CLI wrapper and the install/update manager |

## Documentation

- [docs/API.md](docs/API.md) — the full HTTP API reference
- [DEPLOY.md](DEPLOY.md) — deploying the panel and nodes step by step
- [CONTRIBUTING.md](CONTRIBUTING.md) — setting up locally and sending changes
- [SECURITY.md](SECURITY.md) — how to report a vulnerability
- [CHANGELOG.md](CHANGELOG.md) — what changed, release by release

## Security

If you find a security problem, please don't open a public issue. Report it
privately through GitHub's
[advisory form](https://github.com/Theok09/Xlink/security/advisories/new) —
[SECURITY.md](SECURITY.md) explains what to include and what happens next.

## License

[Apache-2.0](LICENSE) © 2026 ParsaGo92. See [NOTICE](NOTICE) for attribution.
