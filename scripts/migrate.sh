#!/usr/bin/env bash
# Thin wrapper around alembic. Examples:
#   scripts/migrate.sh upgrade head
#   scripts/migrate.sh revision --autogenerate -m "add foo"
#   scripts/migrate.sh downgrade -1
set -euo pipefail
cd "$(dirname "$0")/.."
exec alembic "$@"
