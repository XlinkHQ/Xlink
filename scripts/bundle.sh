#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="${1:-/tmp/xlink.tar.gz}"

export COPYFILE_DISABLE=1

tar \
  --exclude='._*' \
  --exclude='.AppleDouble' \
  --exclude='.DS_Store' \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='web/node_modules' \
  --exclude='.venv' \
  --exclude='.next' \
  --exclude='web/.next' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='.ruff_cache' \
  --exclude='.VSCodeCounter' \
  --exclude='backups' \
  --exclude='.env' \
  --exclude='data' \
  -czf "$OUT" .

echo "bundle: $OUT ($(du -h "$OUT" | cut -f1))"
