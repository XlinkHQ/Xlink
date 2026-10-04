from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ClientTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An operator-authored base document for a subscription format.

    The renderer injects the generated proxies into it, so operators control
    DNS, rules, proxy groups and every other client setting without a panel
    release. At most one template per format is the default (enforced in the
    service so switching the default is a single atomic update).
    """

    __tablename__ = "client_templates"

    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    format: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
