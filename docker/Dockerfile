# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────
# Multi-stage build for XLink. Produces a slim, non-root runtime.
# ─────────────────────────────────────────────────────────────

FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Build deps for asyncpg / argon2-cffi wheels (if no manylinux wheel available)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev

# Install into an isolated prefix we can copy to the runtime stage.
# hatchling builds the wheel from `packages = ["app"]`, so the app tree must be
# present before `pip install .` — copy it here (not just in the runtime stage).
COPY pyproject.toml README.md ./
COPY app ./app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && pip install .

# ─────────────────────────────────────────────────────────────
# Xray-core: used only to run local proxy-latency tests for outbounds.
FROM debian:bookworm-slim AS xray
ARG TARGETARCH
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends curl unzip ca-certificates
ARG XRAY_VERSION=v25.3.6
RUN --mount=type=cache,target=/dl \
    set -eux; \
    case "${TARGETARCH}" in \
      amd64) XA=64 ;; \
      arm64) XA=arm64-v8a ;; \
      *) XA=64 ;; \
    esac; \
    f="/dl/xray-${XRAY_VERSION}-${XA}.zip"; \
    if [ ! -s "$f" ]; then \
      curl -fsSL -o "$f" "https://github.com/XTLS/Xray-core/releases/download/${XRAY_VERSION}/Xray-linux-${XA}.zip"; \
    fi; \
    unzip -o "$f" xray -d /usr/local/bin; \
    chmod +x /usr/local/bin/xray; \
    /usr/local/bin/xray version

# ─────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    XLINK_ENV=production

# Runtime-only system libs
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    curl \
    ca-certificates \
    && groupadd --system --gid 1001 xlink \
    && useradd --system --uid 1001 --gid xlink --create-home --home-dir /home/xlink xlink

COPY --from=xray /usr/local/bin/xray /usr/local/bin/xray

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=xlink:xlink alembic.ini ./
COPY --chown=xlink:xlink alembic ./alembic
COPY --chown=xlink:xlink app ./app
COPY --chown=xlink:xlink node-agent ./node-agent
COPY --chown=xlink:xlink docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh \
    && mkdir -p /app/data/providers \
    && chown -R xlink:xlink /app/data

USER xlink

EXPOSE 8000

ENTRYPOINT ["entrypoint.sh"]
# Gunicorn with uvicorn workers. Worker count is auto-sized to CPUs (capped by
# the DB connection budget) by entrypoint.sh when WEB_CONCURRENCY is unset;
# gunicorn reads WEB_CONCURRENCY natively once the entrypoint exports it. Pin it
# explicitly (env / compose) to override the auto value.
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "60", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
