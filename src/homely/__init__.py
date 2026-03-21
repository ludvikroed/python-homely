"""Reusable Homely client package extracted from the integration."""

__version__ = "0.1.2"

from .client import (
    BASE_URL,
    REQUEST_TIMEOUT,
    HomelyClient,
    auth_header_value,
)
from .exceptions import (
    HomelyAuthError,
    HomelyConnectionError,
    HomelyError,
    HomelyResponseError,
    HomelyWebSocketError,
)
from .models import TokenEndpointResult, TokenResponse
from .websocket import HomelyWebSocket

__all__ = [
    "__version__",
    "BASE_URL",
    "REQUEST_TIMEOUT",
    "HomelyClient",
    "HomelyWebSocket",
    "HomelyError",
    "HomelyConnectionError",
    "HomelyAuthError",
    "HomelyResponseError",
    "HomelyWebSocketError",
    "TokenEndpointResult",
    "TokenResponse",
    "auth_header_value",
]
