from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import tempfile
import time

from app.agent.config_sync import _build_outbound
from app.core.logging import get_logger

logger = get_logger("xlink.outbound_ping")

_XRAY_BIN = os.environ.get("XLINK_XRAY_BIN", "xray")
_TEST_URL = os.environ.get("XLINK_PING_URL", "https://www.gstatic.com/generate_204")
_TEST_TIMEOUT = 8.0
_START_TIMEOUT = 6.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _have_xray() -> bool:
    return shutil.which(_XRAY_BIN) is not None


async def _wait_port(port: int, deadline: float) -> bool:
    while time.monotonic() < deadline:
        try:
            fut = asyncio.open_connection("127.0.0.1", port)
            _, writer = await asyncio.wait_for(fut, timeout=0.5)
            writer.close()
            return True
        except (OSError, TimeoutError):
            await asyncio.sleep(0.15)
    return False


async def _real_ping(type_: str, settings: dict) -> dict:
    built = _build_outbound("proxy-test", type_, settings or {})
    if built is None:
        return {
            "ok": False,
            "latency_ms": None,
            "detail": "Could not build this outbound for testing.",
        }

    socks_port = _free_port()
    config = {
        "log": {"loglevel": "none"},
        "inbounds": [
            {
                "tag": "socks-in",
                "listen": "127.0.0.1",
                "port": socks_port,
                "protocol": "socks",
                "settings": {"udp": False, "auth": "noauth"},
            }
        ],
        "outbounds": [built],
        "routing": {
            "rules": [{"type": "field", "network": "tcp,udp", "outboundTag": "proxy-test"}]
        },
    }

    def _write_config() -> str:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        try:
            json.dump(config, tmp)
        finally:
            tmp.close()
        return tmp.name

    import anyio

    tmp_path = await anyio.to_thread.run_sync(_write_config)

    class _TmpRef:
        name = tmp_path

    tmp = _TmpRef()
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            _XRAY_BIN,
            "run",
            "-c",
            tmp.name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        if not await _wait_port(socks_port, time.monotonic() + _START_TIMEOUT):
            detail = "core failed to start"
            if proc.returncode is not None and proc.stderr is not None:
                err = (await proc.stderr.read()).decode("utf-8", "replace").strip()
                if err:
                    detail = err.splitlines()[-1][:160]
            return {"ok": False, "latency_ms": None, "detail": detail}

        start = time.monotonic()
        curl = await asyncio.create_subprocess_exec(
            "curl",
            "-sS",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            "--max-time",
            str(int(_TEST_TIMEOUT)),
            "--proxy",
            f"socks5h://127.0.0.1:{socks_port}",
            _TEST_URL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(curl.communicate(), timeout=_TEST_TIMEOUT + 2)
        except TimeoutError:
            with __import__("contextlib").suppress(ProcessLookupError):
                curl.kill()
            return {"ok": False, "latency_ms": None, "detail": "timed out"}

        ms = int((time.monotonic() - start) * 1000)
        code = out.decode("ascii", "replace").strip()
        if curl.returncode == 0 and code in ("204", "200"):
            return {"ok": True, "latency_ms": ms, "detail": f"{ms} ms"}
        emsg = err.decode("utf-8", "replace").strip().splitlines()
        return {
            "ok": False,
            "latency_ms": None,
            "detail": (emsg[-1][:160] if emsg else f"HTTP {code or 'no response'}"),
        }
    finally:
        if proc is not None and proc.returncode is None:
            with __import__("contextlib").suppress(ProcessLookupError):
                proc.terminate()
            with __import__("contextlib").suppress(Exception):
                await asyncio.wait_for(proc.wait(), timeout=3)
                if proc.returncode is None:
                    proc.kill()
        with __import__("contextlib").suppress(OSError):
            os.unlink(tmp.name)


async def _tcp_ping(address: str) -> dict:
    from app.agent.config_sync import _parse_host_port

    host, port = _parse_host_port(address.strip())
    if host is None or port is None:
        return {"ok": False, "latency_ms": None, "detail": "Invalid host:port."}
    host = host.strip("[]")
    start = time.monotonic()
    try:
        fut = asyncio.open_connection(host, port)
        _, writer = await asyncio.wait_for(fut, timeout=5.0)
        writer.close()
        with __import__("contextlib").suppress(Exception):
            await writer.wait_closed()
        ms = int((time.monotonic() - start) * 1000)
        return {"ok": True, "latency_ms": ms, "detail": f"{ms} ms (tcp)"}
    except TimeoutError:
        return {"ok": False, "latency_ms": None, "detail": "timed out"}
    except OSError as exc:
        return {"ok": False, "latency_ms": None, "detail": exc.strerror or str(exc)}


async def ping_outbound(type_: str, settings: dict, address: str = "") -> dict:
    if _have_xray() and type_ not in ("block", "blackhole", "dns"):
        try:
            return await _real_ping(type_, settings)
        except Exception as exc:
            logger.warning("real_ping_failed", error=str(exc))
    if address:
        return await _tcp_ping(address)
    return {"ok": False, "latency_ms": None, "detail": "No core available and no address to reach."}
