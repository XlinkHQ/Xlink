# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────
# XLink standalone subscription-page forwarder. Tiny, non-root.
# Independent of the panel image so it can run on a separate host /
# public domain while the panel stays private.
# ─────────────────────────────────────────────────────────────
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system --gid 1001 subpage \
    && useradd --system --uid 1001 --gid subpage --no-create-home subpage

COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && pip install -r requirements.txt

COPY --chown=subpage:subpage app.py ./

USER subpage

EXPOSE 8080

# Single uvicorn process is plenty — this is a thin I/O-bound forwarder and
# scales horizontally by replica. Trust X-Forwarded-* only from a fronting
# proxy; when running standalone on the public edge, clients hit it directly.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
