from __future__ import annotations

import os
import random
import uuid

from locust import HttpUser, between, events, task

API = os.environ.get("XLINK_API_PREFIX", "/api/v1")
ADMIN_USER = os.environ.get("XLINK_ADMIN_USERNAME", "admin")
ADMIN_PASS = os.environ.get("XLINK_ADMIN_PASSWORD", "")

_SEED_TOKENS: list[str] = []
_SEED_NODE: dict[str, str] = {}


def _load_seed() -> None:
    raw = os.environ.get("XLINK_SUB_TOKENS", "")
    if raw:
        _SEED_TOKENS.extend(t.strip() for t in raw.split(",") if t.strip())
    node_id = os.environ.get("XLINK_NODE_ID", "")
    node_token = os.environ.get("XLINK_NODE_TOKEN", "")
    if node_id and node_token:
        _SEED_NODE["id"] = node_id
        _SEED_NODE["token"] = node_token


_load_seed()


class SubscriberUser(HttpUser):
    weight = 8
    wait_time = between(5, 30)

    def on_start(self) -> None:
        self._token = random.choice(_SEED_TOKENS) if _SEED_TOKENS else None
        self._etag: str | None = None

    @task
    def fetch_subscription(self) -> None:
        if not self._token:
            return
        headers = {}
        if self._etag:
            headers["If-None-Match"] = self._etag
        with self.client.get(
            f"{API}/subscriptions/sub/{self._token}?format=base64",
            headers=headers,
            name="sub:fetch",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304):
                if resp.status_code == 200:
                    self._etag = resp.headers.get("etag")
                resp.success()
            else:
                resp.failure(f"sub fetch {resp.status_code}")


class AdminUser(HttpUser):
    weight = 1
    wait_time = between(1, 5)

    def on_start(self) -> None:
        self._access: str | None = None
        if not ADMIN_PASS:
            return
        r = self.client.post(
            f"{API}/auth/login",
            json={"identifier": ADMIN_USER, "password": ADMIN_PASS},
            name="admin:login",
        )
        if r.status_code == 200:
            self._access = r.json().get("tokens", {}).get("access_token")

    @property
    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access}"} if self._access else {}

    @task(5)
    def list_users(self) -> None:
        if not self._access:
            return
        self.client.get(f"{API}/users?size=25", headers=self._auth, name="admin:list_users")

    @task(2)
    def dashboard_summary(self) -> None:
        if not self._access:
            return
        self.client.get(f"{API}/monitoring/summary", headers=self._auth, name="admin:summary")

    @task(1)
    def create_and_delete_user(self) -> None:
        if not self._access:
            return
        uname = f"lt-{uuid.uuid4().hex[:12]}"
        r = self.client.post(
            f"{API}/users",
            json={"username": uname, "password": "LoadTest-Pw-12345!"},
            headers=self._auth,
            name="admin:create_user",
        )
        if r.status_code in (200, 201):
            uid = r.json().get("id")
            if uid:
                self.client.delete(
                    f"{API}/users/{uid}", headers=self._auth, name="admin:delete_user"
                )


class NodeAgent(HttpUser):
    weight = 2
    wait_time = between(8, 15)

    def on_start(self) -> None:
        self._id = _SEED_NODE.get("id")
        self._token = _SEED_NODE.get("token")
        self._version: str | None = None

    @property
    def _hdr(self) -> dict[str, str]:
        return {"X-Agent-Token": self._token} if self._token else {}

    @task(3)
    def poll_config(self) -> None:
        if not self._id:
            return
        params = f"?known_version={self._version}" if self._version else ""
        with self.client.get(
            f"{API}/agent/nodes/{self._id}/config{params}",
            headers=self._hdr,
            name="agent:config",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                self._version = resp.json().get("config_version") or self._version
                resp.success()
            elif resp.status_code == 304:
                resp.success()
            else:
                resp.failure(f"config {resp.status_code}")

    @task(1)
    def report_traffic(self) -> None:
        if not self._id:
            return
        self.client.post(
            f"{API}/agent/nodes/{self._id}/traffic",
            json={
                "node_id": self._id,
                "batch_id": uuid.uuid4().hex,
                "samples": [],
            },
            headers=self._hdr,
            name="agent:traffic",
        )


@events.test_start.add_listener
def _on_start(environment, **_kwargs) -> None:
    if not _SEED_TOKENS:
        print("WARNING: no XLINK_SUB_TOKENS set — SubscriberUser will be a no-op.")
    if not ADMIN_PASS:
        print("WARNING: no XLINK_ADMIN_PASSWORD set — AdminUser will be a no-op.")
    if not _SEED_NODE:
        print("WARNING: no XLINK_NODE_ID/XLINK_NODE_TOKEN set — NodeAgent will be a no-op.")
