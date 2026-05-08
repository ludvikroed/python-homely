"""Reusable Homely client package extracted from the integration."""

__version__ = "0.1.5"

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
from .websocket import (
    WEBSOCKET_STATUS_OPTIONS,
    HomelyWebSocket,
    WebSocketConnectionState,
    normalize_websocket_status,
)

__all__ = [
    "__version__",
    "BASE_URL",
    "REQUEST_TIMEOUT",
    "HomelyClient",
    "HomelyWebSocket",
    "WebSocketConnectionState",
    "HomelyError",
    "HomelyConnectionError",
    "HomelyAuthError",
    "HomelyResponseError",
    "HomelyWebSocketError",
    "TokenEndpointResult",
    "TokenResponse",
    "WEBSOCKET_STATUS_OPTIONS",
    "auth_header_value",
    "normalize_websocket_status",
]
