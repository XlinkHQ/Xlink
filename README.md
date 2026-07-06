# Xlink

Multi-node VPN management panel — FastAPI + PostgreSQL + Redis backend, Next.js admin console, and a pull-based node agent.

Supports **xray, sing-box, hysteria, wireguard** cores (vless / vmess / trojan / shadowsocks / hysteria2 / tuic / wireguard) with per-user data/expiry/device limits, multi-node load-balancing + failover, traffic accounting, and backups.

## Quick start

```bash
cp .env.example .env
# set XLINK_JWT_SECRET_KEY (openssl rand -hex 32), XLINK_POSTGRES_PASSWORD,
# and XLINK_ADMIN_USERNAME / XLINK_ADMIN_PASSWORD

make install     # generate secret, build, migrate, start
```

Open the panel at `http://localhost:3000` and log in with the `XLINK_ADMIN_*` credentials.

## Commands

```bash
make up | make down | make deploy | make logs
./xlink user list
./xlink admin reset-password -u admin -p NEWPASS
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

[MIT](LICENSE) © 2026 ParsaGo92
