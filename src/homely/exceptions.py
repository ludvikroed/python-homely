"""Exceptions exposed by the Homely SDK."""
from __future__ import annotations


class HomelyError(Exception):
    """Base exception for Homely SDK failures."""


class HomelyConnectionError(HomelyError):
    """Raised when the Homely service cannot be reached."""


class HomelyAuthError(HomelyError):
    """Raised when Homely rejects authentication or authorization."""


class HomelyResponseError(HomelyError):
    """Raised when Homely returns an unexpected response."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        body: str | None = None,
        body_preview: str | None = None,
    ) -> None:
        """Initialize the exception with optional response details."""
        super().__init__(message)
        self.status = status
        if body_preview is None:
            body_preview = body
        self.body_preview = body_preview
        self.body = body


class HomelyWebSocketError(HomelyError):
    """Raised when the Homely websocket cannot be established."""
