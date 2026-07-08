#!/usr/bin/env bash
# Container entrypoint. Migrations are run by a dedicated `migrate` service in
# compose / a Job in k8s — NOT here — so multiple API replicas don't race on
# `alembic upgrade`.
set -euo pipefail

# Auto-size the gunicorn worker pool to the host's CPUs, but never past what the
# database can serve. The operator can always pin it explicitly with
# WEB_CONCURRENCY / XLINK_WEB_CONCURRENCY.
#
#   workers = min( (2*cores)+1 , floor(max_server_conns / per_worker_conns) )
#
# per_worker_conns = pool_size + max_overflow (each worker owns its own pool).
# With PgBouncer/transaction pooling the client pool is tiny and shared, so we
# skip the DB cap and just scale to CPU. An explicit value is honoured verbatim.
if [ -z "${WEB_CONCURRENCY:-}" ] && [ -z "${XLINK_WEB_CONCURRENCY:-}" ]; then
  cores="$(nproc 2>/dev/null || echo 1)"
  cpu_workers=$(( cores * 2 + 1 ))

  pool_size="${XLINK_DB_POOL_SIZE:-10}"
  overflow="${XLINK_DB_MAX_OVERFLOW:-10}"
  max_conns="${XLINK_DB_MAX_SERVER_CONNECTIONS:-100}"
  pool_mode="${XLINK_DB_POOL_MODE:-session}"

  workers="$cpu_workers"
  if [ "$pool_mode" != "transaction" ]; then
    per_worker=$(( pool_size + overflow ))
    [ "$per_worker" -lt 1 ] && per_worker=1
    # Leave ~15% of server connections for migrate/psql/superuser headroom.
    budget=$(( max_conns * 85 / 100 ))
    db_workers=$(( budget / per_worker ))
    [ "$db_workers" -lt 1 ] && db_workers=1
    [ "$workers" -gt "$db_workers" ] && workers="$db_workers"
  fi
  [ "$workers" -lt 1 ] && workers=1

  export WEB_CONCURRENCY="$workers"
  export XLINK_WEB_CONCURRENCY="$workers"
  echo "[entrypoint] auto workers=$workers (cores=$cores, pool_mode=$pool_mode)"
fi

exec "$@"
