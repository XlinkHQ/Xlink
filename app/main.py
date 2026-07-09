from __future__ import annotations

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.lifespan import lifespan
from app.middleware.audit import AuditMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.observability.prometheus import PrometheusMetrics, PrometheusMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.project_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url=(
            f"{settings.api_v1_prefix}/openapi.json" if not settings.is_production else None
        ),
    )

    # Private Prometheus registry + metric objects for this app instance. The
    # middleware records request count/latency into it (in-process only, no I/O);
    # the /metrics endpoint below serializes it. Stashed on app.state so the
    # lifespan can start the leader-gated domain-gauge collector against it.
    prometheus = PrometheusMetrics()
    app.state.prometheus = prometheus

    # Starlette runs middleware in REVERSE registration order (last-added is
    # outermost). We want TrustedHost outermost (cheaply reject spoofed-Host junk
    # before any DB/Redis work) and RequestContext innermost. So register in the
    # order they should EXECUTE reversed: innermost first, outermost last.
    app.add_middleware(PrometheusMiddleware, metrics=prometheus)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(AuditMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, production=settings.is_production)
    if settings.cors_origins:
        wildcard = "*" in settings.cors_origins
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            # Credentials cannot be combined with a wildcard origin (the browser
            # rejects it, and it is unsafe). Only enable them for explicit origins.
            allow_credentials=not wildcard,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )
    app.add_middleware(
        RateLimitMiddleware,
        limit_per_minute=settings.rate_limit_per_minute,
        enabled=settings.rate_limit_enabled,
        fail_open=settings.rate_limit_fail_open,
        trusted_proxy_ips=settings.trusted_proxy_ips,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.trusted_hosts or ["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    import hmac

    from starlette.responses import PlainTextResponse

    from app.observability.prometheus import CONTENT_TYPE_LATEST

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics(request: Request) -> Response:
        # Opt-in and OFF by default: with no token configured the scrape
        # endpoint does not exist (404), so nothing changes for existing
        # deploys. This path is deliberately separate from the admin API auth
        # and from the agent /metrics INGEST + admin /monitoring summary.
        cfg = request.app.state.xlink.settings
        token = cfg.metrics_token
        if token is None:
            return PlainTextResponse("Not Found", status_code=404)
        secret = token.get_secret_value()
        auth = request.headers.get("authorization", "")
        scheme, _, presented = auth.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(presented, secret):
            return PlainTextResponse(
                "Unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        # Cheap: serialize in-memory gauges/counters only. Domain gauges are
        # refreshed out-of-band by the background collector, not here.
        body = request.app.state.prometheus.render()
        return Response(content=body, media_type=CONTENT_TYPE_LATEST)

    from app.dependencies.core import CacheDep
    from app.services.acme_issuer import get_challenge

    @app.get("/.well-known/acme-challenge/{token}", include_in_schema=False)
    async def acme_http_challenge(token: str, cache: CacheDep) -> Response:
        value = await get_challenge(cache, token)
        if value is None:
            return Response(status_code=404)
        return Response(content=value, media_type="text/plain")

    return app


app = create_app()
