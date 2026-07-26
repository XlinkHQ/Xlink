from __future__ import annotations

import asyncio
import ipaddress
import os
import platform
import shutil
import signal
import socket
import urllib.request
import uuid

import anyio
from fastapi import APIRouter, Response

from app.core.config import APP_VERSION, get_settings
from app.dependencies.auth import AdminUser, SudoAdminUser
from app.dependencies.core import CacheDep
from app.dependencies.services import MonitoringServiceDep
from app.monitoring.schemas import MetricRead, MetricsSnapshotRead, SystemStatsRead

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

_background_tasks: set[asyncio.Task[None]] = set()


def _meminfo() -> dict[str, int]:
    out: dict[str, int] = {}
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                if key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                    out[key] = int(rest.split()[0]) * 1024
    except OSError:
        pass
    return out


def _process_count() -> int:
    try:
        return sum(1 for name in os.listdir("/proc") if name.isdigit())
    except OSError:
        return 0


def _uptime_seconds() -> int:
    try:
        with open("/proc/uptime") as fh:
            return int(float(fh.read().split()[0]))
    except OSError:
        return 0


def _cpu_percent(cores: int) -> float:
    try:
        load1 = os.getloadavg()[0]
    except (OSError, AttributeError):
        return 0.0
    if cores <= 0:
        return 0.0
    return round(min(100.0, (load1 / cores) * 100.0), 1)


_HOST_OS_PATHS = (
    "/host/os-release",
    "/host/etc/os-release",
    "/host/usr/lib/os-release",
)
_CONTAINER_OS_PATHS = ("/etc/os-release", "/usr/lib/os-release")


def _parse_os_release(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        with open(path) as fh:
            for line in fh:
                key, sep, val = line.partition("=")
                if sep:
                    out[key.strip()] = val.strip().strip('"')
    except OSError:
        return {}
    return out


def _host_os_release() -> dict[str, str]:
    env_override = os.environ.get("XLINK_HOST_OS_RELEASE")
    if env_override:
        parsed = _parse_os_release(env_override)
        if parsed:
            return parsed
    for path in _HOST_OS_PATHS:
        parsed = _parse_os_release(path)
        if parsed:
            return parsed
    return {}


def _os_release() -> dict[str, str]:
    host = _host_os_release()
    if host:
        return host
    for path in _CONTAINER_OS_PATHS:
        parsed = _parse_os_release(path)
        if parsed:
            return parsed
    return {}


def _os_release_value(key: str) -> str:
    return _os_release().get(key, "")


def _os_pretty_name() -> str:
    data = _os_release()
    pretty = data.get("PRETTY_NAME") or data.get("NAME", "")
    version = data.get("VERSION", "") or data.get("VERSION_ID", "")
    if pretty:
        return pretty if data.get("PRETTY_NAME") else f"{pretty} {version}".strip()
    return f"{platform.system()} {platform.release()}".strip()


def _os_slug() -> str:
    return _os_release_value("ID").lower()


def _primary_ip6() -> str:
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        try:
            s.connect(("2001:4860:4860::8888", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return ""


def _local_egress_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def _public_ip_lookup() -> str:
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:  # noqa: S310
                ip = resp.read().decode().strip()
            ipaddress.ip_address(ip)
            return ip
        except Exception:
            continue
    return ""


def _primary_ip() -> str:
    local = _local_egress_ip()
    try:
        if not ipaddress.ip_address(local).is_private:
            return local
    except ValueError:
        pass
    return _public_ip_lookup() or local


def _mac_address() -> str:
    node = uuid.getnode()
    return ":".join(f"{(node >> e) & 0xFF:02x}" for e in range(40, -8, -8))


_static_host: dict | None = None


def _host_static() -> dict:
    global _static_host
    if _static_host is None:
        settings = get_settings()
        _static_host = {
            "cpu_cores": os.cpu_count() or 1,
            "hostname": socket.gethostname(),
            "os_name": _os_pretty_name(),
            "os_slug": _os_slug(),
            "kernel": platform.release(),
            "arch": platform.machine(),
            "ip_address": settings.public_ip or _primary_ip(),
            "ip6_address": _primary_ip6(),
            "mac_address": settings.public_mac or _mac_address(),
            "python_version": platform.python_version(),
            "app_version": APP_VERSION,
        }
    return _static_host


def _collect_system_stats() -> SystemStatsRead:
    st = _host_static()
    cores = st["cpu_cores"]
    mem = _meminfo()
    mem_total = mem.get("MemTotal", 0)
    mem_avail = mem.get("MemAvailable", 0)
    swap_total = mem.get("SwapTotal", 0)
    swap_free = mem.get("SwapFree", 0)
    disk = shutil.disk_usage("/")
    try:
        load1, load5, load15 = os.getloadavg()
    except (OSError, AttributeError):
        load1 = load5 = load15 = 0.0
    return SystemStatsRead(
        cpu_percent=_cpu_percent(cores),
        ram_used_bytes=max(0, mem_total - mem_avail),
        ram_total_bytes=mem_total,
        disk_used_bytes=disk.used,
        disk_total_bytes=disk.total,
        uptime_seconds=_uptime_seconds(),
        load_avg_1=round(load1, 2),
        load_avg_5=round(load5, 2),
        load_avg_15=round(load15, 2),
        swap_used_bytes=max(0, swap_total - swap_free),
        swap_total_bytes=swap_total,
        process_count=_process_count(),
        **st,
    )


def _snapshot_read(snapshot) -> MetricsSnapshotRead:
    return MetricsSnapshotRead(
        metrics=tuple(
            MetricRead(name=m.name, value=m.value, labels=dict(m.labels)) for m in snapshot.metrics
        ),
        collected_at=snapshot.collected_at,
    )


@router.get("/summary", response_model=MetricsSnapshotRead)
async def monitoring_summary(
    _admin: AdminUser,
    monitoring: MonitoringServiceDep,
) -> MetricsSnapshotRead:
    return _snapshot_read(await monitoring.snapshot())


@router.get("/metrics", response_model=list[MetricRead])
async def monitoring_metrics(
    _admin: AdminUser,
    monitoring: MonitoringServiceDep,
) -> list[MetricRead]:
    snapshot = await monitoring.snapshot()
    return [MetricRead(name=m.name, value=m.value, labels=dict(m.labels)) for m in snapshot.metrics]


@router.post("/restart", status_code=202)
async def monitoring_restart(_admin: SudoAdminUser) -> dict[str, str]:

    async def _bye() -> None:
        await asyncio.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)

    task = asyncio.create_task(_bye())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"status": "restarting"}


@router.get("/prometheus", response_class=Response)
async def monitoring_prometheus(
    _admin: AdminUser,
    monitoring: MonitoringServiceDep,
) -> Response:
    body = await monitoring.prometheus()
    return Response(content=body, media_type="text/plain; version=0.0.4")


_SYSTEM_CACHE_KEY = "xlink:monitoring:system"


@router.get("/system", response_model=SystemStatsRead)
async def monitoring_system(_admin: AdminUser, cache: CacheDep) -> SystemStatsRead:
    cached = await cache.get_json(_SYSTEM_CACHE_KEY)
    if cached is not None:
        return SystemStatsRead(**cached)
    stats = await anyio.to_thread.run_sync(_collect_system_stats)
    await cache.set_json(_SYSTEM_CACHE_KEY, stats.model_dump(mode="json"), ttl=3)
    return stats
