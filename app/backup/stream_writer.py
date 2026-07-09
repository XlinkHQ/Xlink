from __future__ import annotations

import contextlib
import functools
import hashlib
import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anyio
from pydantic_core import to_jsonable_python

from app.backup.exporter import (
    stream_rows,
    stream_traffic_metadata,
    table_specs,
)
from app.backup.models import BackupScope
from app.backup.validator import _CANONICAL_SEPARATORS, canonical_row
from app.db.session import Database

# The document's top-level ``data`` keys, in the order the streaming writer emits
# them. This MUST equal the sorted order that ``json.dumps(..., sort_keys=True)``
# produces, so the accumulated checksum is byte-identical to ``checksum_payload``
# over the fully-materialised document.
_DATA_KEYS_SORTED = ("assignments", "nodes", "profiles", "traffic_metadata", "users")

_FILE_INDENT = 2
_PAD = " " * _FILE_INDENT

# Flush the human-readable buffer to disk once it exceeds this many chars. Bounds
# in-memory buffering to a few KB regardless of dataset size.
_FLUSH_THRESHOLD = 64 * 1024


class _StreamingChecksum:
    """Accumulates the canonical (sorted-key, compact-separator) JSON of the
    ``data`` object into a running sha256 without ever holding the whole
    document. The byte stream it hashes is identical to
    ``json.dumps(data, sort_keys=True, separators=(",",":"))``."""

    def __init__(self) -> None:
        self._h = hashlib.sha256()
        self._member_started = False

    def _feed(self, text: str) -> None:
        self._h.update(text.encode("utf-8"))

    def begin_object(self) -> None:
        self._feed("{")

    def key(self, name: str) -> None:
        if self._member_started:
            self._feed(_CANONICAL_SEPARATORS[0])
        self._member_started = True
        self._feed(json.dumps(name, separators=_CANONICAL_SEPARATORS))
        self._feed(_CANONICAL_SEPARATORS[1])

    def begin_array(self) -> None:
        self._feed("[")

    def array_element(self, canonical: str, *, first: bool) -> None:
        if not first:
            self._feed(_CANONICAL_SEPARATORS[0])
        self._feed(canonical)

    def end_array(self) -> None:
        self._feed("]")

    def end_object(self) -> str:
        self._feed("}")
        return self._h.hexdigest()


def _pretty_row(row: dict[str, Any]) -> str:
    """Human-readable row body, indented to sit three levels deep in the file.
    Values are normalised with ``to_jsonable_python`` — the SAME normalisation
    the checksum uses — so the checksum recomputed over the reloaded file matches
    the stored checksum (the file round-trips and restores cleanly). Whitespace
    is irrelevant to the importer, which json.loads() the file."""
    pretty = json.dumps(to_jsonable_python(row), indent=_FILE_INDENT)
    return pretty.replace("\n", "\n" + _PAD * 3)


async def stream_export_to_file(
    db: Database,
    *,
    target: Path,
    tmp: Path,
    scope: BackupScope = BackupScope.FULL,
    since: datetime | None = None,
) -> Path:
    """Stream a full backup document to ``tmp`` row-by-row with bounded memory,
    then atomically rename it onto ``target``.

    The DB is read through async server-side cursors (``stream_scalars`` +
    ``yield_per``) so at most one batch of rows is resident at a time. File I/O
    runs on a worker thread so the event loop is never blocked. The produced file
    is a valid backup document with the exact same structure and checksum the
    in-memory exporter would emit."""

    exported_at = datetime.now(UTC).isoformat()
    checksum = _StreamingChecksum()
    specs = {key: (model, redacted) for key, model, redacted in table_specs()}

    def _open() -> Any:
        # 0600 from creation — backups carry cleartext node/proxy secrets.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        return os.fdopen(fd, "w", encoding="utf-8")

    fh = await anyio.to_thread.run_sync(_open)
    buf: list[str] = []
    buf_len = 0

    async def flush() -> None:
        nonlocal buf, buf_len
        if not buf:
            return
        chunk = "".join(buf)
        buf = []
        buf_len = 0
        await anyio.to_thread.run_sync(fh.write, chunk)

    def emit(text: str) -> None:
        nonlocal buf_len
        buf.append(text)
        buf_len += len(text)

    try:
        emit(
            "{\n"
            f'{_PAD}"schema_version": 1,\n'
            f'{_PAD}"scope": {json.dumps(scope.value)},\n'
            f'{_PAD}"exported_at": {json.dumps(exported_at)},\n'
            f'{_PAD}"data": {{'
        )
        checksum.begin_object()

        async with db.sessionmaker() as session:
            for k_idx, data_key in enumerate(_DATA_KEYS_SORTED):
                checksum.key(data_key)
                checksum.begin_array()
                emit(("," if k_idx else "") + f'\n{_PAD * 2}"{data_key}": [')

                rows: AsyncIterator[dict[str, Any]]
                if data_key == "traffic_metadata":
                    rows = stream_traffic_metadata(session, since=since)
                else:
                    model, redacted = specs[data_key]
                    rows = stream_rows(session, model, since=since, redacted=redacted)

                first = True
                async for row in rows:
                    checksum.array_element(canonical_row(row), first=first)
                    emit(("" if first else ",") + f"\n{_PAD * 3}{_pretty_row(row)}")
                    first = False
                    if buf_len >= _FLUSH_THRESHOLD:
                        await flush()

                checksum.end_array()
                emit(f"\n{_PAD * 2}]")

        digest = checksum.end_object()
        emit(f"\n{_PAD}}},\n{_PAD}\"checksum\": {json.dumps(digest)}\n}}\n")
        await flush()
    finally:
        await anyio.to_thread.run_sync(fh.close)

    # Atomic publish: rename is atomic on the same filesystem, so a reader never
    # sees a half-written backup and a crash mid-write leaves only the tmp file.
    await anyio.to_thread.run_sync(functools.partial(os.replace, tmp, target))
    with contextlib.suppress(OSError):
        os.chmod(target, 0o600)
    return target


def prune_backups(directory: Path, keep: int) -> int:
    backups = sorted(directory.glob("xlink-backup-*.json"))
    for stale in backups[: max(0, len(backups) - keep)]:
        with contextlib.suppress(OSError):
            stale.unlink()
    return min(len(backups), keep)
