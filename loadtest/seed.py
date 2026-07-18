from __future__ import annotations

import asyncio
import os
import sys
import uuid

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import Database
from app.domain.user import User, UserRole
from app.subscription.schemas import FeedScope
from app.subscription.tokens import create_subscription_token

COUNT = int(os.environ.get("SEED_COUNT", "1000"))


async def main() -> None:
    settings = get_settings()
    db = Database(settings)
    tokens: list[str] = []
    async with db.session() as session:
        for _ in range(COUNT):
            uid = uuid.uuid4()
            session.add(
                User(
                    id=uid,
                    username=f"seed-{uid.hex[:12]}",
                    role=UserRole.USER,
                    hashed_password=hash_password("SeedUser-Pw-12345!"),
                    is_active=True,
                )
            )
            tokens.append(create_subscription_token(uid, FeedScope.USER, settings))
        await session.commit()
    out = os.environ.get("SEED_TOKENS_FILE", "loadtest/.sub_tokens")
    with open(out, "w") as fh:
        fh.write(",".join(tokens))
    print(f"seeded {COUNT} users; wrote {len(tokens)} sub tokens to {out}", file=sys.stderr)
    print(",".join(tokens))


if __name__ == "__main__":
    asyncio.run(main())
