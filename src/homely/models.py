"""Public data models for the Homely SDK."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TokenFailureReason = Literal[
    "invalid_auth",
    "invalid_refresh_token",
    "http_error",
    "network_error",
    "timeout",
    "invalid_json",
    "invalid_payload",
    "empty_response",
]


@dataclass(slots=True)
class TokenResponse:
    """Typed token response returned by the Homely authentication endpoints."""

    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    raw: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenResponse:
        """Build a typed token response from a raw API payload."""
        expires_in = data.get("expires_in")
        try:
            parsed_expires_in = int(expires_in) if expires_in is not None else None
        except (TypeError, ValueError):
            parsed_expires_in = None

        return cls(
            access_token=str(data["access_token"]),
            refresh_token=data.get("refresh_token"),
            expires_in=parsed_expires_in,
            raw=dict(data),
        )


@dataclass(slots=True)
class TokenEndpointResult:
    """Detailed result returned by authentication and refresh helpers."""

    token: TokenResponse | None = None
    reason: TokenFailureReason | None = None
    status: int | None = None
    detail: str | None = None
    body_preview: str | None = None

    @property
    def ok(self) -> bool:
        """Return whether the request produced a usable token response."""
        return self.token is not None

    @property
    def raw(self) -> dict[str, Any] | None:
        """Return the raw token payload when available."""
        if self.token is None:
            return None
        return self.token.raw
