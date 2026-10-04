"""Entrypoint for a jobs-only process (``XLINK_INSTANCE_ROLE=worker``).

The worker deliberately reuses the FastAPI ``lifespan`` rather than wiring the
jobs a second time: one wiring path means a job added to lifespan is picked up
here automatically, and there is no second copy to drift out of sync. The app it
mounts serves nothing — under the ``worker`` role, lifespan starts neither the
HTTP listener's gRPC server nor the audit writer, so no port is bound.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

from fastapi import FastAPI

from app.core.config import InstanceRole, get_settings
from app.core.lifespan import lifespan
from app.core.logging import configure_logging, get_logger

logger = get_logger("xlink.worker")


async def run() -> None:
    settings = get_settings()
    configure_logging(settings)

    if not settings.instance_role.runs_jobs:
        logger.warning(
            "worker_role_runs_no_jobs",
            role=settings.instance_role.value,
            hint="set XLINK_INSTANCE_ROLE=worker (or all)",
        )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    app = FastAPI(lifespan=lifespan)
    async with lifespan(app):
        logger.info("worker_ready", role=settings.instance_role.value)
        await stop.wait()
        logger.info("worker_stopping")


def main() -> int:
    settings = get_settings()
    if settings.instance_role is InstanceRole.API:
        logger.error("worker_started_with_api_role", role=settings.instance_role.value)
        return 1
    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
