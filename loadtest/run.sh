#!/usr/bin/env bash
set -euo pipefail

# XLink load test runner. Proves the 10k-user / 50-node scale claim.
#
# Usage:
#   loadtest/run.sh <target-host> [users] [spawn-rate] [duration]
# Example (10k concurrent, ramp 200/s, 10 min):
#   XLINK_ADMIN_PASSWORD=... loadtest/run.sh http://127.0.0.1:8000 10000 200 10m
#
# Env:
#   XLINK_ADMIN_PASSWORD   admin password (AdminUser tasks; required for admin load)
#   XLINK_SUB_TOKENS       comma-separated sub tokens (or auto-loaded from .sub_tokens)
#   XLINK_NODE_ID          a real node id (NodeAgent tasks)
#   XLINK_NODE_TOKEN       that node's agent token
#   SEED_COUNT             how many users to seed first (default 1000)

HOST="${1:-http://127.0.0.1:8000}"
USERS="${2:-1000}"
RATE="${3:-50}"
DURATION="${4:-5m}"

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

if [ ! -f loadtest/.sub_tokens ] && [ -z "${XLINK_SUB_TOKENS:-}" ]; then
  echo "No sub tokens found — seeding ${SEED_COUNT:-1000} users..."
  .venv/bin/python loadtest/seed.py >/dev/null
fi
if [ -f loadtest/.sub_tokens ] && [ -z "${XLINK_SUB_TOKENS:-}" ]; then
  export XLINK_SUB_TOKENS="$(cat loadtest/.sub_tokens)"
fi

exec .venv/bin/locust \
  -f loadtest/locustfile.py \
  --host "$HOST" \
  --users "$USERS" \
  --spawn-rate "$RATE" \
  --run-time "$DURATION" \
  --headless \
  --csv loadtest/report \
  --html loadtest/report.html
