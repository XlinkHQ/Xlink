from __future__ import annotations

import asyncio
import base64
import secrets

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import Settings
from app.db.session import Database
from app.domain.client_assignment import ClientAssignment
from app.domain.profile import Profile
from app.providers.base.models import ProviderKind


async def main() -> None:
    settings = Settings()
    db = Database(settings)
    updated = 0
    generated = 0
    skipped = 0
    try:
        async with db.session() as session:
            rows = (
                await session.execute(
                    select(ClientAssignment, Profile)
                    .join(Profile, ClientAssignment.profile_id == Profile.id)
                    .where(ClientAssignment.provider_kind == ProviderKind.WIREGUARD)
                )
            ).all()
            for assignment, profile in rows:
                creds = dict(assignment.credentials or {})
                if creds.get("preshared_key"):
                    skipped += 1
                    continue
                psk = str((profile.settings or {}).get("presharedKey") or "").strip()
                if not psk:
                    psk = base64.b64encode(secrets.token_bytes(32)).decode()
                    generated += 1
                else:
                    updated += 1
                creds["preshared_key"] = psk
                assignment.credentials = creds
                flag_modified(assignment, "credentials")
            await session.commit()
    finally:
        await db.dispose()
    print(
        f"wg-psk-backfill: from_profile={updated} generated={generated} "
        f"already_had={skipped} total={updated + generated + skipped}"
    )


if __name__ == "__main__":
    asyncio.run(main())
