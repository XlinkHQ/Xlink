from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.core.config import Settings
from app.core.security import hash_password
from app.db.session import Database
from app.domain.user import User, UserRole


async def run(email: str, username: str, password: str) -> int:
    if len(password) < 12:
        print("Password must be at least 12 characters.", file=sys.stderr)
        return 2

    domain = email.rsplit("@", 1)[-1].lower()
    if domain.endswith((".local", ".localhost", ".test", ".invalid", ".example")):
        print(f"Email domain '{domain}' is reserved and rejected by validation.", file=sys.stderr)
        return 2

    db = Database(Settings())
    async with db.session() as session:
        existing = await session.scalar(
            select(User).where((User.email == email.lower()) | (User.username == username))
        )
        if existing is not None:
            existing.email = email.lower()
            existing.role = UserRole.ADMIN
            existing.hashed_password = hash_password(password)
            existing.is_active = True
            await session.flush()
            print(f"Updated existing user '{existing.username}' to admin.")
            await db.dispose()
            return 0

        user = User(
            email=email.lower(),
            username=username,
            full_name="Administrator",
            hashed_password=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        print(f"Created admin user '{username}'.")
    await db.dispose()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or promote an XLink admin user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.email, args.username, args.password)))


if __name__ == "__main__":
    main()
