from __future__ import annotations

import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client.gc_collector import GCCollector
from prometheus_client.platform_collector import PlatformCollector
from prometheus_client.process_collector import ProcessCollector
from starlette.types import ASGIApp, Message, Receive, Scope, Send

__all__ = [
    "CONTENT_TYPE_LATEST",
    "PrometheusMetrics",
    "PrometheusMiddleware",
]

_LATENCY_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


class PrometheusMetrics:
    """Owns a private CollectorRegistry plus the app's metric objects.

    A private registry (not the global default) keeps repeated app
    construction — tests build a fresh app per case — from raising duplicate
    timeseries errors, and isolates our series from any other library that
    touches the global registry.
    """

    def __init__(self) -> None:
        self.registry = CollectorRegistry(auto_describe=True)

        ProcessCollector(registry=self.registry)
        PlatformCollector(registry=self.registry)
        GCCollector(registry=self.registry)

        self.http_requests_total = Counter(
            "xlink_http_requests_total",
            "Total HTTP requests processed.",
            labelnames=("method", "route", "status"),
            registry=self.registry,
        )
        self.http_request_duration_seconds = Histogram(
            "xlink_http_request_duration_seconds",
            "HTTP request latency in seconds.",
            labelnames=("method", "route"),
            buckets=_LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.http_requests_in_progress = Gauge(
            "xlink_http_requests_in_progress",
            "In-flight HTTP requests.",
            labelnames=("method",),
            registry=self.registry,
        )

        self.users_total = Gauge(
            "xlink_users_total",
            "Total users.",
            registry=self.registry,
        )
        self.users_active = Gauge(
            "xlink_users_active",
            "Active (enabled) users.",
            registry=self.registry,
        )
        self.nodes_total = Gauge(
            "xlink_nodes_total",
            "Total nodes.",
            registry=self.registry,
        )
        self.nodes_online = Gauge(
            "xlink_nodes_online",
            "Nodes reporting online/active.",
            registry=self.registry,
        )
        self.assignments_active = Gauge(
            "xlink_assignments_active",
            "Active client assignments.",
            registry=self.registry,
        )
        self.traffic_bytes_total = Gauge(
            "xlink_traffic_bytes_total",
            "Total traffic in bytes across all nodes/users.",
            registry=self.registry,
        )
        self.domain_metrics_up = Gauge(
            "xlink_domain_metrics_up",
            "1 when domain gauges were refreshed from a fresh summary, else 0.",
            registry=self.registry,
        )

    def render(self) -> bytes:
        return generate_latest(self.registry)


def _route_template(scope: Scope) -> str:
    """Return the matched route's path template, or a bounded fallback.

    Starlette sets ``scope["route"]`` once routing resolves (before the
    response starts), so this is populated by the time our send-wrapper sees
    ``http.response.start``. Using ``route.path`` (e.g. ``/users/{user_id}``)
    instead of the raw path keeps label cardinality bounded.
    """
    route = scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return "__unmatched__"


class PrometheusMiddleware:
    """Lightweight ASGI middleware recording request count + latency.

    Always installed, but it only touches in-process counters — no I/O, no DB —
    so it is safe to run regardless of whether the /metrics endpoint is enabled.
    """

    def __init__(self, app: ASGIApp, metrics: PrometheusMetrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        start = time.perf_counter()
        status_code = 500
        in_progress = self.metrics.http_requests_in_progress.labels(method=method)
        in_progress.inc()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            in_progress.dec()
            route = _route_template(scope)
            self.metrics.http_requests_total.labels(
                method=method, route=route, status=str(status_code)
            ).inc()
            self.metrics.http_request_duration_seconds.labels(
                method=method, route=route
            ).observe(duration)
