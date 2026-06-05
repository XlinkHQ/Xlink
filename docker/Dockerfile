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
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install into an isolated prefix we can copy to the runtime stage
COPY pyproject.toml README.md ./
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && pip install .

# ─────────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    XLINK_ENV=production

# Runtime-only system libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 xlink \
    && useradd --system --uid 1001 --gid xlink --no-create-home xlink

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=xlink:xlink alembic.ini ./
COPY --chown=xlink:xlink alembic ./alembic
COPY --chown=xlink:xlink app ./app
COPY --chown=xlink:xlink docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh

USER xlink

EXPOSE 8000

ENTRYPOINT ["entrypoint.sh"]
# Gunicorn with uvicorn workers; worker count tuned via env at deploy time.
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "60", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
