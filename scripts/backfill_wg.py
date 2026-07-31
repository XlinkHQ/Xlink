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


def _server_prefix(profile: Profile) -> str:
    addr = str((profile.settings or {}).get("address") or "")
    if "." in addr:
        head = addr.split("/")[0].strip().rsplit(".", 1)[0]
        if head:
            return head
    return "10.8.0"


async def main() -> None:
    settings = Settings()
    db = Database(settings)
    psk_set = 0
    addr_set = 0
    total = 0
    try:
        async with db.session() as session:
            rows = (
                await session.execute(
                    select(ClientAssignment, Profile)
                    .join(Profile, ClientAssignment.profile_id == Profile.id)
                    .where(ClientAssignment.provider_kind == ProviderKind.WIREGUARD)
                    .order_by(ClientAssignment.node_id, ClientAssignment.id)
                )
            ).all()
            used_by_node: dict[object, set[int]] = {}
            for assignment, profile in rows:
                prefix = _server_prefix(profile)
                used = used_by_node.setdefault((assignment.node_id, prefix), {1})
                addr = (assignment.credentials or {}).get("address")
                if isinstance(addr, str) and addr.startswith(prefix + "."):
                    tail = addr.split("/")[0].rsplit(".", 1)[-1]
                    if tail.isdigit():
                        used.add(int(tail))
            for assignment, profile in rows:
                total += 1
                creds = dict(assignment.credentials or {})
                changed = False
                if not creds.get("preshared_key"):
                    psk = str((profile.settings or {}).get("presharedKey") or "").strip()
                    if not psk:
                        psk = base64.b64encode(secrets.token_bytes(32)).decode()
                    creds["preshared_key"] = psk
                    psk_set += 1
                    changed = True
                addr = creds.get("address")
                prefix = _server_prefix(profile)
                is_client_addr = (
                    isinstance(addr, str)
                    and addr.startswith(prefix + ".")
                    and not addr.split("/")[0].endswith(".1")
                    and addr.endswith("/32")
                )
                if not is_client_addr:
                    used = used_by_node.setdefault((assignment.node_id, prefix), {1})
                    octet = next(o for o in range(2, 255) if o not in used)
                    used.add(octet)
                    creds["address"] = f"{prefix}.{octet}/32"
                    addr_set += 1
                    changed = True
                if changed:
                    assignment.credentials = creds
                    flag_modified(assignment, "credentials")
            await session.commit()
    finally:
        await db.dispose()
    print(f"wg-backfill: preshared_key_set={psk_set} address_set={addr_set} total={total}")


if __name__ == "__main__":
    asyncio.run(main())
