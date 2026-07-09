<div align="center">

<img src="docs/assets/logo.png" alt="XLink" width="420" />

### Multi-node VPN management panel for xray, sing-box, hysteria, and WireGuard

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](pyproject.toml)
[![Next.js 15](https://img.shields.io/badge/Next.js-15-black.svg)](web/package.json)

</div>

---

## Overview

XLink is a self-hosted control plane for operating a VPN service across many
servers from a single console. You register your nodes, create users, and hand
each user one subscription link; the panel distributes the correct configuration
to every node, meters real traffic per user, enforces quotas and expiry, and
moves users off a node automatically when it goes offline.

It is built for the point where single-server panels stop scaling — where configs
end up copied by hand and per-user accounting is unreliable, particularly on
WireGuard, which most panels cannot meter per user at all. In XLink a user is a
first-class account with a data cap, an expiry, and a device limit, and traffic is
measured on every core, WireGuard included.

The panel never initiates connections into a node. Each node runs a lightweight
agent that reaches out to the panel, pulls the configuration it should be running,
applies it locally, and reports traffic and health back. A node therefore needs
only outbound access to the panel's API — no inbound exposure, no shared SSH
credentials, no push access from the panel.

## Features

**Cores and protocols.** xray, sing-box, hysteria, and WireGuard, selected per
profile. Together they cover vless, vmess, trojan, shadowsocks, shadowtls,
hysteria2, tuic, naive, socks, and wireguard, each with the transport and TLS
options its core supports (including REALITY and xtls-rprx-vision on xray).

**Users as accounts.** Per-user data cap, fixed-date or start-on-first-use
expiry, HWID-aware device limits, and scheduled usage resets. Each user has a
single HMAC-signed, per-user, revocable subscription token that the panel renders
into whatever the client requests — plain list, base64, sing-box JSON,
Clash/Mihomo YAML, xray JSON, or a per-protocol URI — chosen from the client's
user-agent.

**Fleet and reliability.** Any number of nodes with load-balancing and automatic
failover. The agent delivers traffic through a write-ahead log, so a dropped
connection never double-counts or loses usage; it reports health each cycle and
can install, update, or restart individual cores on command. Hourly traffic
rollups keep analytics fast as data grows. Certificates are issued through ACME on
the bundled edge proxy, so HTTPS is automatic once a domain is set.

**Access control and operations.** Role-based access with sudo admins and scoped
reseller-admins that see only their own users, groups, and profiles. Audit log,
GitOps config sync, a recurring-job scheduler, notifications, configurable
retention, database backups, and an optional Prometheus metrics endpoint.
Everything the console does is available through API keys, an official Python SDK,
and a full CLI.

## Architecture

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

The panel is a FastAPI backend with a Next.js console, backed by PostgreSQL and
Redis. The backend is deliberately layered — `api → services → repositories → db`,
with the domain models and schemas free of any dependency on the layers above — so
it stays testable and the boundaries hold over time. It runs multiple Gunicorn
workers (auto-sized to the host CPUs, capped by the database connection budget),
elects a single leader in Redis for background jobs, and can offload read-heavy
analytics to an optional PostgreSQL read replica. A full walk-through with
diagrams is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md); interactive API docs
are served at `http://<panel>:8000/docs` outside production.

## Installation

On a fresh Linux server, as root:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/XlinkHQ/Xlink/main/scripts/install.sh)
```

The installer performs the entire setup: it installs Docker if it is missing,
clones the repository to `/opt/xlink`, prompts for the web port and an optional
secret admin path, generates fresh secrets into `.env`, pulls (or builds) the
images, runs the database migrations, starts the full stack, and prints the panel
URL together with a one-time admin password.

> [!TIP]
> Re-running the same command updates an existing installation in place; your
> `.env` is preserved. Append `--build` to build the images locally instead of
> pulling them from the registry.

To follow the steps manually instead of the one-liner, see [DEPLOY.md](DEPLOY.md).

**Requirements:** a Linux host with Docker; roughly 2 GB RAM and 2 CPUs for a
comfortable single-box install (the installer adds swap guidance for smaller
hosts).

> [!NOTE]
> Point a domain at the server first if you want automatic HTTPS — the bundled
> edge proxy issues certificates through ACME once `XLINK_DOMAIN` is set.

## Operating the panel

From the install directory, the `xlink` command wraps day-to-day operations:

```bash
xlink up | down | restart | status | logs
xlink update                 # pull the latest release, migrate, restart
xlink backup                 # snapshot the database
xlink edit                   # edit .env, then restart
```

Every administrative action is also available on the CLI, which runs inside the
api container:

```bash
xlink admin reset-password -u admin -p NEWPASS   # recover a locked-out admin
xlink admin create -u reseller --no-sudo         # a scoped reseller-admin
xlink user list [--status S] [--owner ADMIN]
xlink user create -u alice --limit 50 --expire 2026-12-31
xlink user show -u alice                          # details and subscription link
xlink node create -n edge-1 --host 203.0.113.10 --port 443
xlink node token edge-1                            # issue an agent token (shown once)
```

Run `xlink help` for the complete command list.

## Adding a node

Registering a location takes two steps. In the console, under **Nodes**, add the
node with its public host and core port and provision an agent token — the console
returns a node id and a token. Then, on the node server, run the agent installer
with those values:

```bash
curl -fsSL https://<panel-host>:8000/agent/install.sh \
  | sudo -E bash -s https://<panel-host> <node-id> <agent-token>
```

The installer sets up every core by default; restrict it with
`--cores=xray,wireguard` when a node only needs some. Follow the agent with
`journalctl -u xlink-agent -f` — once it logs `pulled config` it is talking to the
panel, and the node turns **active** in the console within about thirty seconds.

## Configuration

All configuration is environment-driven, and the installer writes a complete
`.env` with generated secrets, so most deployments never edit it by hand. The full
set of keys is documented in [.env.example](.env.example); the ones most commonly
adjusted are:

| Variable | Purpose | Default |
| -------- | ------- | ------- |
| `XLINK_DOMAIN` | Public domain; enables the ACME/HTTPS edge proxy when set | unset (plain ports) |
| `XLINK_ACME_EMAIL` | Contact address for Let's Encrypt | — |
| `XLINK_WEB_PORT` | Web UI port on the host | `3000` |
| `XLINK_WEB_PATH` | Serve the panel under a secret path instead of `/` | `/` |
| `XLINK_PORT` | API port that nodes connect to | `8000` |
| `XLINK_PUBLIC_IP` | Override the server IP shown on the dashboard | auto-detected |
| `XLINK_JWT_SECRET_KEY` | Signs authentication and subscription tokens | generated |
| `XLINK_POSTGRES_REPLICA_HOST` | Optional read replica for analytics reads | none |
| `XLINK_METRICS_TOKEN` | Enables the bearer-guarded Prometheus `/metrics` endpoint | disabled |
| `XLINK_LOG_JSON` | Structured JSON logs (recommended in production) | `false` |

> [!IMPORTANT]
> Secrets live only in `.env` on the panel server. It is git-ignored and must
> never be committed.

## Development

Requirements: Python 3.13+, [uv](https://docs.astral.sh/uv/), Node.js, and Docker.

```bash
uv sync --extra dev                    # backend dependencies
docker compose up -d postgres redis    # datastores
uv run alembic upgrade head            # migrations
uv run ./scripts/dev.sh                # run the API

cd web && npm install && npm run dev   # the console, in another terminal
```

The full contributor workflow, coding standards, and the checks that must pass
before a pull request are in [CONTRIBUTING.md](CONTRIBUTING.md). In short, CI
requires:

```bash
ruff check . && ruff format --check .          # lint and formatting
mypy app                                       # backend type checking
uv run pytest                                  # backend test suite
cd web && ./node_modules/.bin/tsc --noEmit     # web type checking
```

> [!WARNING]
> Do not run `next build` during development. The dev server is expected to be
> running, and a parallel production build corrupts `.next`. Use `tsc --noEmit`
> to type-check the web app.

## Repository layout

| Path | Contents |
| ---- | -------- |
| `app/` | FastAPI backend (`api → services → repositories → db`) |
| `app/api/v1/routers/` | HTTP endpoints, one module per domain |
| `app/subscription/` | Subscription feed generator, per-format renderers, token layer |
| `app/agent/` | Node-facing plane: config sync, commands, traffic ingest, IP limits |
| `app/traffic/` | Traffic accounting, hourly rollups, retention |
| `app/failover/` | Node-down detection and user migration |
| `web/` | Next.js admin console |
| `node-agent/` | The pull-based agent that runs on each node |
| `sdk/python/` | Official Python SDK for the HTTP API |
| `alembic/` | Database migrations (single head) |
| `scripts/`, `xlink`, `xlink.sh` | Installer, CLI wrapper, and install/update manager |

## Documentation

| Document | Description |
| -------- | ----------- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and data model, with diagrams |
| [docs/API.md](docs/API.md) | Complete HTTP API reference |
| [sdk/python/](sdk/python/) | Official Python SDK and usage examples |
| [DEPLOY.md](DEPLOY.md) | Panel and node deployment, step by step |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Local setup and contribution workflow |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting policy |
| [CHANGELOG.md](CHANGELOG.md) | Release history |

## Security

Report vulnerabilities privately through GitHub's private advisory form rather
than a public issue. The full policy and what to include are in
[SECURITY.md](SECURITY.md).

## License

Licensed under the [Apache License 2.0](LICENSE). © 2026 ParsaGo92. See
[NOTICE](NOTICE) for attribution.
