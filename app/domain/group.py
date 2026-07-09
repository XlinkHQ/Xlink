from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import BigInteger, Column, ForeignKey, String, Table
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.domain.profile import Profile

SLUG_PATTERN = r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$"

# Association table linking groups to the profiles they contain. Mirrors the
# ``admin_groups`` table (see app/domain/user.py): composite PK on the pair,
# both FKs CASCADE so deleting a group or profile prunes its rows. Replaces the
# old JSON ``profile_ids`` column, which was unindexable — "which groups contain
# profile X" now becomes an indexed JOIN instead of a full-table Python scan.
group_profiles = Table(
    "group_profiles",
    Base.metadata,
    Column(
        "group_id",
        PGUUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "profile_id",
        PGUUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Group(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "groups"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # Eager (selectin) so the collection is always populated when a Group is
    # loaded — keeps ``profile_ids`` serialization safe in the async router
    # context without a lazy-load round-trip.
    profiles: Mapped[list[Profile]] = relationship(
        "Profile", secondary=group_profiles, lazy="selectin"
    )

    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    __mapper_args__: ClassVar[dict[str, Any]] = {"version_id_col": version}

    @property
    def profile_ids(self) -> list[uuid.UUID]:
        """Convenience view over the ``profiles`` relationship so existing
        callers/serializers (GroupRead, CLI) keep reading ``group.profile_ids``
        unchanged. Read-only — writes go through the repository join-table API."""
        return [p.id for p in self.profiles]
