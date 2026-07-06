#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec ./xlink.sh install "${1:-pull}"
