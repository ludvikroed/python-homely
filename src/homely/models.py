"""Public data models for the Homely SDK."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
