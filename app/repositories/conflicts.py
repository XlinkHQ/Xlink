from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError

ConflictRule = tuple[Sequence[str], str, str]


def conflict_from_integrity(
    exc: IntegrityError,
    rules: Sequence[ConflictRule],
    fallback_message: str,
    fallback_code: str,
) -> ConflictError:
    detail = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
    for substrings, message, code in rules:
        if any(substring in detail for substring in substrings):
            return ConflictError(message, code=code)
    return ConflictError(fallback_message, code=fallback_code)
