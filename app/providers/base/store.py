from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_DEFAULT_DATA_DIR = os.environ.get("XLINK_DATA_DIR", "data/providers")


class JsonClientStore:
    """Multi-process-safe JSON-backed client store.

    The on-disk file is the source of truth. Every mutation reloads the current
    file under an exclusive lock, applies the single operation against fresh
    data, then atomically rewrites — so concurrent gunicorn workers cannot clob-
    ber each other's writes or resurrect deleted keys. Reads also reload.
    """

    def __init__(self, provider_name: str, *, data_dir: str | None = None) -> None:
        base = Path(data_dir) if data_dir else Path(_DEFAULT_DATA_DIR)
        base.mkdir(parents=True, exist_ok=True)
        self._path = base / f"{provider_name}_clients.json"
        self._lock_path = base / f"{provider_name}_clients.lock"

    def __contains__(self, key: str) -> bool:
        with self._locked():
            return key in self._read()

    def exists(self) -> bool:
        return self._path.exists()

    def __getitem__(self, key: str) -> dict[str, Any]:
        with self._locked():
            return self._read()[key]

    def get(self, key: str, default: Any = None) -> Any:
        with self._locked():
            return self._read().get(key, default)

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        with self._locked():
            data = self._read()
            data[key] = value
            self._write(data)

    def __delitem__(self, key: str) -> None:
        with self._locked():
            data = self._read()
            del data[key]
            self._write(data)

    def pop(self, key: str, *args: Any) -> Any:
        with self._locked():
            data = self._read()
            result = data.pop(key, *args)
            self._write(data)
            return result

    @contextmanager
    def _locked(self):
        with open(self._lock_path, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}
        with open(self._path) as fh:
            try:
                data = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                data = {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, dict[str, Any]]) -> None:
        tmp_path = self._path.with_suffix(".tmp")
        with open(tmp_path, "w") as fh:
            json.dump(data, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, self._path)
