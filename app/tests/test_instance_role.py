"""The api/worker split is a deployment-shape change, so the contract worth
pinning is: which process starts which background work, and that nothing binds a
port twice."""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI

from app.core.config import InstanceRole, Settings
from app.core.lifespan import lifespan

# Every job field AppState carries, i.e. the things a worker owns.
_JOB_FIELDS = (
    "cleanup_job",
    "metrics_job",
    "traffic_retention_job",
    "traffic_rollup_job",
    "agent_reconcile_job",
    "assignment_expiration_job",
    "notification_job",
    "node_agent_scheduler",
    "backup_job",
    "cert_renewal_job",
    "domain_metrics_collector",
)


def _settings(role: InstanceRole, db_path: str) -> Settings:
    # acme_email switches on a job that is otherwise off by default, so
    # "worker runs everything" is actually exercised.
    return Settings(
        database_url_override=f"sqlite+aiosqlite:///{db_path}",
        instance_role=role,
        acme_email="ops@example.com",
        grpc_enabled=False,  # no real port binding in tests
        admin_username="",  # skip the bootstrap path entirely
    )


@asynccontextmanager
async def _boot(monkeypatch, role: InstanceRole, tmp_path):
    """Run lifespan under a role and hand back the resulting AppState.

    A context manager, not a bare generator: lifespan's shutdown must run so the
    engine is disposed, otherwise the leaked connection trips
    `filterwarnings = ["error"]`.
    """
    import fakeredis.aioredis

    from app.db.base import Base
    from app.db.redis import RedisCache
    from app.db.session import Database

    settings = _settings(role, str(tmp_path / "role.db"))
    monkeypatch.setattr("app.core.lifespan.get_settings", lambda: settings)

    real_init = RedisCache.__init__

    def _fake_init(self, s) -> None:
        real_init(self, s)
        self._client = fakeredis.aioredis.FakeRedis(decode_responses=False)

    monkeypatch.setattr(RedisCache, "__init__", _fake_init)

    # lifespan bootstraps the admin user, so the schema has to exist first —
    # otherwise that path fails and leaks the connection, which
    # `filterwarnings = ["error"]` escalates into an unrelated test failure.
    seed = Database(settings)
    async with seed.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed.dispose()

    app = FastAPI()
    async with lifespan(app):
        yield app.state.xlink


@pytest.mark.parametrize("role", [InstanceRole.ALL, InstanceRole.WORKER])
async def test_job_running_roles_start_the_jobs(monkeypatch, role, tmp_path) -> None:
    async with _boot(monkeypatch, role, tmp_path) as state:
        started = [f for f in _JOB_FIELDS if getattr(state, f) is not None]
        assert started, f"{role.value} should run background jobs"


async def test_api_role_starts_no_background_jobs(monkeypatch, tmp_path) -> None:
    """The whole point of the split: an API replica must not also run the jobs."""
    async with _boot(monkeypatch, InstanceRole.API, tmp_path) as state:
        running = [f for f in _JOB_FIELDS if getattr(state, f) is not None]
        assert running == [], f"api role started jobs: {running}"


async def test_api_role_still_drains_the_audit_outbox(monkeypatch, tmp_path) -> None:
    """Audit rows are written by request handlers, so the HTTP role drains them."""
    async with _boot(monkeypatch, InstanceRole.API, tmp_path) as state:
        assert state.audit_writer is not None


async def test_worker_role_does_not_drain_the_audit_outbox(monkeypatch, tmp_path) -> None:
    async with _boot(monkeypatch, InstanceRole.WORKER, tmp_path) as state:
        assert state.audit_writer is None


def test_role_capabilities_are_mutually_consistent() -> None:
    assert InstanceRole.ALL.serves_http and InstanceRole.ALL.runs_jobs
    assert InstanceRole.API.serves_http and not InstanceRole.API.runs_jobs
    assert InstanceRole.WORKER.runs_jobs and not InstanceRole.WORKER.serves_http
    # No role may be inert.
    for r in InstanceRole:
        assert r.serves_http or r.runs_jobs


def test_default_role_preserves_single_process_behaviour() -> None:
    s = Settings(database_url_override="sqlite+aiosqlite:///:memory:")
    assert s.instance_role is InstanceRole.ALL
