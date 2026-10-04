"""Durable background job queue on Redis Streams.

Before this, side-effect work such as webhook / Discord / Telegram delivery ran
as fire-and-forget ``asyncio`` tasks held in process memory: a restart or crash
mid-delivery lost it silently, and a failed send was logged once and dropped.

Guarantees:

* **Survives a crash.** A message stays in the consumer group's pending list
  until it is ``XACK``-ed. If the process dies mid-job, ``XAUTOCLAIM`` hands
  the message to a live worker once it has been idle past the visibility
  timeout.
* **Retries with backoff.** A failed job is parked in a delayed set and
  re-enqueued after ``base_backoff * 2**attempt`` seconds.
* **Dead-letters.** After ``max_attempts`` the job moves to a dead-letter
  stream, where it can be inspected and retried by an operator rather than
  vanishing.
* **Safe with many workers.** Consumer groups deliver each message to exactly
  one consumer, so no leader lock is needed to avoid double processing.

Delivery is at-least-once: a crash after the side effect but before the ack
re-runs the job, so handlers must tolerate a repeat.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import socket
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.logging import get_logger

logger = get_logger("xlink.queue")

Handler = Callable[[dict[str, Any]], Awaitable[None]]

STREAM = "xlink:jobs"
DEAD = "xlink:jobs:dead"
DELAYED = "xlink:jobs:delayed"
CLAIMS = "xlink:jobs:claims"
GROUP = "xlink-workers"
# Pause after an empty poll. Bounds idle CPU even when BLOCK is not honoured.
_IDLE_WAIT_S = 0.25


def _s(v: Any) -> str:
    return v.decode() if isinstance(v, bytes) else str(v)


def _id_lt(a: str, b: str) -> bool:
    """Stream ids are `<ms>-<seq>`; compare numerically, not as strings."""
    am, _, aseq = a.partition("-")
    bm, _, bseq = b.partition("-")
    return (int(am), int(aseq or 0)) < (int(bm), int(bseq or 0))


class DurableQueue:
    def __init__(
        self,
        client: Any,
        *,
        consumer: str | None = None,
        visibility_timeout_ms: int = 60_000,
        max_attempts: int = 5,
        base_backoff: float = 2.0,
        max_backoff: float = 300.0,
    ) -> None:
        self._r = client
        self._consumer = consumer or f"{socket.gethostname()}:{os.getpid()}"
        self._visibility_ms = visibility_timeout_ms
        self._max_attempts = max_attempts
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff
        self._handlers: dict[str, Handler] = {}
        self._group_ready = False
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    # ------------------------------------------------------------------ setup
    def register(self, kind: str, handler: Handler) -> None:
        self._handlers[kind] = handler

    async def _ensure_group(self) -> None:
        if self._group_ready:
            return
        try:
            await self._r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self._group_ready = True

    # ------------------------------------------------------------------ produce
    async def enqueue(
        self, kind: str, payload: dict[str, Any], *, max_attempts: int | None = None
    ) -> str:
        await self._ensure_group()
        msg_id = await self._r.xadd(
            STREAM,
            {
                "kind": kind,
                "payload": json.dumps(payload),
                "attempt": "0",
                "max_attempts": str(max_attempts or self._max_attempts),
                "enqueued_at": str(time.time()),
            },
        )
        return _s(msg_id)

    # ------------------------------------------------------------------ consume
    async def _promote_delayed(self) -> int:
        """Move retries whose backoff has elapsed back onto the stream."""
        now = time.time()
        due = await self._r.zrangebyscore(DELAYED, 0, now, start=0, num=100)
        moved = 0
        for raw in due:
            # ZREM first: only the worker that wins the removal re-enqueues,
            # so two workers promoting at once cannot duplicate a retry.
            if await self._r.zrem(DELAYED, raw):
                fields = json.loads(_s(raw))
                await self._r.xadd(STREAM, fields)
                moved += 1
        return moved

    async def _reclaim_stale(self) -> list[tuple[Any, dict[Any, Any]]]:
        """Take over messages whose consumer died mid-job."""
        try:
            res = await self._r.xautoclaim(
                STREAM, GROUP, self._consumer, min_idle_time=self._visibility_ms,
                start_id="0-0", count=20,
            )
        except Exception as exc:
            logger.warning("queue_reclaim_failed", error=str(exc))
            return []
        entries = res[1] if len(res) > 1 else []
        out = []
        for msg_id, fields in entries:
            if not fields:
                continue
            # A message that keeps killing its worker is a poison pill: count
            # reclaims and dead-letter it rather than crash-looping forever.
            n = int(await self._r.hincrby(CLAIMS, _s(msg_id), 1))
            if n > self._max_attempts:
                await self._dead_letter(
                    msg_id, fields, "worker crashed processing this job repeatedly"
                )
                continue
            logger.warning("queue_reclaimed_stale_job", msg_id=_s(msg_id), reclaims=n)
            out.append((msg_id, fields))
        return out

    async def _trim(self) -> None:
        """Drop entries that are delivered AND acknowledged — never anything else.

        Acked entries are deliberately not XDEL-ed on the hot path: deleting the
        tail of a stream and appending again in the same millisecond can mint an
        id at or below the group cursor on some implementations, and
        `XREADGROUP >` then skips that message for good. A plain MAXLEN would
        be just as wrong in the other direction, cutting undelivered backlog.
        The floor here is the older of the group cursor and the oldest pending
        message, so only fully finished work is removed.
        """
        try:
            groups = await self._r.xinfo_groups(STREAM)
        except Exception:
            return
        if not groups:
            return
        floor = _s(groups[0].get("last-delivered-id", b"0-0"))
        pending = await self._r.xpending(STREAM, GROUP)
        if isinstance(pending, dict) and pending.get("pending") and pending.get("min"):
            oldest = _s(pending["min"])
            if _id_lt(oldest, floor):
                floor = oldest
        if floor and floor != "0-0":
            # MINID keeps `floor` itself; everything strictly older goes.
            await self._r.xtrim(STREAM, minid=floor, approximate=False)

    async def run_once(self, *, block_ms: int = 1000) -> int:
        """Process one batch. Returns how many messages were handled."""
        await self._ensure_group()
        await self._promote_delayed()
        batch = await self._reclaim_stale()
        resp = await self._r.xreadgroup(
            GROUP, self._consumer, {STREAM: ">"}, count=10, block=block_ms
        )
        for _stream, entries in resp or []:
            batch.extend(entries)
        for msg_id, fields in batch:
            await self._process(msg_id, fields)
        if batch:
            await self._trim()
        return len(batch)

    async def _process(self, msg_id: Any, fields: dict[Any, Any]) -> None:
        f = {_s(k): _s(v) for k, v in fields.items()}
        kind = f.get("kind", "")
        handler = self._handlers.get(kind)
        if handler is None:
            await self._dead_letter(msg_id, fields, f"no handler for kind {kind!r}")
            return
        try:
            payload = json.loads(f.get("payload") or "{}")
            await handler(payload)
        except asyncio.CancelledError:
            raise  # leave it pending; another worker reclaims it
        except Exception as exc:
            await self._retry_or_dead(msg_id, f, exc)
            return
        await self._r.xack(STREAM, GROUP, msg_id)
        await self._r.hdel(CLAIMS, _s(msg_id))

    async def _retry_or_dead(self, msg_id: Any, f: dict[str, str], exc: Exception) -> None:
        attempt = int(f.get("attempt", "0")) + 1
        max_attempts = int(f.get("max_attempts", str(self._max_attempts)))
        if attempt >= max_attempts:
            await self._dead_letter(msg_id, f, f"{type(exc).__name__}: {exc}")
            return
        delay = min(self._max_backoff, self._base_backoff * (2 ** (attempt - 1)))
        retry = {**f, "attempt": str(attempt), "last_error": f"{type(exc).__name__}: {exc}"[:500]}
        await self._r.zadd(DELAYED, {json.dumps(retry, sort_keys=True): time.time() + delay})
        await self._r.xack(STREAM, GROUP, msg_id)
        await self._r.hdel(CLAIMS, _s(msg_id))
        logger.warning(
            "queue_job_retry", kind=f.get("kind"), attempt=attempt, delay_s=delay, error=str(exc)
        )

    async def _dead_letter(self, msg_id: Any, fields: dict[Any, Any], reason: str) -> None:
        f = {_s(k): _s(v) for k, v in fields.items()}
        await self._r.xadd(DEAD, {**f, "reason": reason[:500], "dead_at": str(time.time())})
        await self._r.xack(STREAM, GROUP, msg_id)
        await self._r.hdel(CLAIMS, _s(msg_id))
        logger.error("queue_job_dead_lettered", kind=f.get("kind"), reason=reason)

    # ------------------------------------------------------------------ operate
    async def stats(self) -> dict[str, int]:
        await self._ensure_group()
        pending = await self._r.xpending(STREAM, GROUP)
        info = await self._r.xinfo_stream(STREAM)
        groups = await self._r.xinfo_groups(STREAM)
        added = int(info.get("entries-added", 0) or 0)
        read = int((groups[0].get("entries-read") or 0) if groups else 0)
        return {
            "queued": max(0, added - read),
            "in_flight": int(pending.get("pending", 0) if isinstance(pending, dict) else 0),
            "delayed": int(await self._r.zcard(DELAYED)),
            "dead": int(await self._r.xlen(DEAD)),
        }

    async def dead_letters(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = await self._r.xrevrange(DEAD, count=limit)
        out = []
        for msg_id, fields in rows:
            f = {_s(k): _s(v) for k, v in fields.items()}
            out.append({
                "id": _s(msg_id),
                "kind": f.get("kind"),
                "attempt": int(f.get("attempt", "0")),
                "reason": f.get("reason"),
                "dead_at": float(f.get("dead_at", "0") or 0),
                "enqueued_at": float(f.get("enqueued_at", "0") or 0),
            })
        return out

    async def retry_dead(self, dead_id: str) -> bool:
        rows = await self._r.xrange(DEAD, min=dead_id, max=dead_id)
        if not rows:
            return False
        _, fields = rows[0]
        f = {_s(k): _s(v) for k, v in fields.items()}
        await self.enqueue(f["kind"], json.loads(f.get("payload") or "{}"),
                           max_attempts=int(f.get("max_attempts", str(self._max_attempts))))
        await self._r.xdel(DEAD, dead_id)
        return True

    async def discard_dead(self, dead_id: str) -> bool:
        return bool(await self._r.xdel(DEAD, dead_id))

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self._task is None:
            self._stopping.clear()
            self._task = asyncio.create_task(self._run(), name="durable-queue")
            logger.info("queue_started", consumer=self._consumer, kinds=sorted(self._handlers))

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                handled = await self.run_once(block_ms=1000)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("queue_loop_error")
                handled = 0
                idle = 2.0
            else:
                idle = _IDLE_WAIT_S
            if handled == 0:
                # Never rely on the server honouring BLOCK. If XREADGROUP comes
                # back immediately (a Redis-compatible proxy, an error path, a
                # test double) and nothing here suspends, `await` never yields:
                # the loop spins at 100% CPU and starves every other task on the
                # event loop — including the API it shares a process with.
                # Waiting on the stop event is a real suspension point.
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stopping.wait(), timeout=idle)

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
