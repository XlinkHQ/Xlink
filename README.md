# Xlink

Multi-node VPN management panel — FastAPI + PostgreSQL + Redis backend, Next.js admin console, and a pull-based node agent.

Supports **xray, sing-box, hysteria, wireguard** cores (vless / vmess / trojan / shadowsocks / hysteria2 / tuic / wireguard) with per-user data/expiry/device limits, multi-node load-balancing + failover, traffic accounting, and backups.

## Install (one command)

On a fresh server, as root:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Theok09/Xlink/main/scripts/install.sh)
```

It installs Docker if missing, clones the repo to `/opt/xlink`, generates fresh
secrets, builds/pulls the images, runs migrations, starts everything, and prints
the panel URL + one-time admin password. Re-run it any time to update.

Force a local build (no registry): append `--build`.

## Manage

```bash
xlink up | down | restart | status | logs
xlink update            # pull latest, migrate, restart
xlink backup            # snapshot the database
xlink cli user list
xlink admin reset-password -u admin -p NEWPASS
```

## Stack

`web (:3000)` → `api (:8000)` → `migrate` → `postgres` + `redis`.

Clean layering: `api → services → repositories → db`; `domain` and `schemas` are dependency-free.

API docs: `http://localhost:8000/docs`

## Development

```bash
docker compose up -d postgres redis
pip install -e ".[dev]"
alembic upgrade head
./scripts/dev.sh
cd web && npm install && npm run dev

ruff check . && mypy app && pytest
```

## License

[Apache-2.0](LICENSE) © 2026 ParsaGo92
