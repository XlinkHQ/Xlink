from __future__ import annotations

from typing import Any


class XLinkError(Exception):
    """Base class for all SDK errors."""


class XLinkAPIError(XLinkError):
    """Raised when the panel returns a non-2xx response.

    The panel wraps every handled error in an envelope::

        {"error": {"code": "conflict", "message": "...", "details": {...}}}

    ``code`` and ``message`` are parsed from that envelope when present;
    otherwise they fall back to the HTTP status.
    """

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"[{status} {code}] {message}")

    @classmethod
    def from_response(cls, status: int, body: Any) -> XLinkAPIError:
        code = "error"
        message = "Request failed."
        details: dict[str, Any] | None = None
        if isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, dict):
                code = str(err.get("code") or code)
                message = str(err.get("message") or message)
                raw_details = err.get("details")
                if isinstance(raw_details, dict):
                    details = raw_details
            elif "detail" in body:
                message = str(body["detail"])
        return cls(status=status, code=code, message=message, details=details)
