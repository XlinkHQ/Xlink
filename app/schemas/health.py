from __future__ import annotations

from typing import Literal

from app.schemas.base import APIModel


class LivenessResponse(APIModel):
    status: Literal["ok"] = "ok"


class DependencyHealth(APIModel):
    database: bool
    redis: bool


class ReadinessResponse(APIModel):
    status: Literal["ready", "degraded"]
    dependencies: DependencyHealth
