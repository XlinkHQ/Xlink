#!/usr/bin/env bash
# Run the API locally with hot reload against compose-provided Postgres + Redis.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "No .env found — copying from .env.example" >&2
  cp .env.example .env
fi

exec uvicorn app.main:app --reload --host "${XLINK_HOST:-0.0.0.0}" --port "${XLINK_PORT:-8000}"
