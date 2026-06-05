#!/usr/bin/env bash
# Container entrypoint. Migrations are run by a dedicated `migrate` service in
# compose / a Job in k8s — NOT here — so multiple API replicas don't race on
# `alembic upgrade`. This entrypoint just execs the given command.
set -euo pipefail

exec "$@"
