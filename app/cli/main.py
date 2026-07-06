from __future__ import annotations

import asyncio
import shlex
import sys

from app.cli.runner import run_cli
from app.core.config import Settings
from app.db.redis import RedisCache
from app.db.session import Database


async def _run(argv: list[str]) -> str:
    settings = Settings()
    db = Database(settings)
    cache = RedisCache(settings)
    try:
        async with db.session() as session:
            return await run_cli(session, cache, settings, shlex.join(argv))
    finally:
        await db.dispose()


def main() -> int:
    argv = sys.argv[1:] or ["help"]
    print(asyncio.run(_run(argv)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
