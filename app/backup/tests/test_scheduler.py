from __future__ import annotations

import json
from pathlib import Path

from app.backup.scheduler import run_backup
from app.db.session import Database


async def test_run_backup_writes_file(db: Database, tmp_path: Path) -> None:
    target = await run_backup(db, directory=tmp_path, keep=7)

    assert target.exists()
    assert target.parent == tmp_path
    payload = json.loads(target.read_text())
    assert payload["scope"] == "full"
    assert "data" in payload


async def test_run_backup_prunes_to_keep(db: Database, tmp_path: Path) -> None:

    for i in range(5):
        (tmp_path / f"xlink-backup-2000010{i}T000000Z.json").write_text("{}")

    await run_backup(db, directory=tmp_path, keep=3)

    remaining = sorted(tmp_path.glob("xlink-backup-*.json"))
    assert len(remaining) == 3

    assert remaining[-1].read_text() != "{}"
