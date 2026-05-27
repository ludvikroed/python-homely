"""Reusable WebSocket client for Homely real-time updates."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import aiohttp

from .exceptions import HomelyWebSocketError

_LOGGER = logging.getLogger(__name__)
WEBSOCKET_STATUS_OPTIONS = (
    "not_initialized",
    "connecting",
    "connected",
    "disconnected",
    "unknown",
)
_WEBSOCKET_STATUS_OPTION_SET = frozenset(WEBSOCKET_STATUS_OPTIONS)


@dataclass(frozen=True)
class WebSocketConnectionState:
    """Normalized websocket status shared across integrations and tooling."""

    connected: bool
    reported_status: str
    effective_status: str
    reason: str | None
    status_mismatch: bool


def _log_identifier(value: str | int | None) -> str | None:
    """Return a shortened identifier suitable for logs."""
    if value is None:
        return None

    text = str(value)
    if len(text) <= 8:
        return text
    return f"{text[:8]}..."


def normalize_websocket_status(value: Any) -> str:
    """Convert websocket labels to stable enum values."""
    if not isinstance(value, str):
        return "unknown"

    normalized = value.strip().lower().replace(" ", "_")
    return (
        normalized
        if normalized in _WEBSOCKET_STATUS_OPTION_SET
        else "unknown"
    )


def _socket_transport_is_connected(socket: Any | None) -> bool:
    """Return True when the Socket.IO or Engine.IO transport is still alive."""
    if socket is None:
        return False

    try:
        if bool(socket.connected):
            return True
    except Exception:
        pass

    engineio_client = getattr(socket, "eio", None)
    try:
        return str(getattr(engineio_client, "state", "")).lower() == "connected"
    except Exception:
        return False


class HomelyWebSocket:
    """WebSocket client for Homely using Socket.IO."""

    WEBSOCKET_URL = "https://sdk.iotiliti.cloud"

    def __init__(
        self,
        location_id: str | int,
        token: str,
        on_data_update: Callable[[dict[str, Any]], None],
        status_update_callback: Callable[[str, str | None], None] | None = None,
        context_id: str | None = None,
        entry_id: str | None = None,
    ) -> None:
        """Initialize WebSocket client."""
        self.context_id = context_id or entry_id
        self.entry_id = self.context_id
        self.location_id = location_id
        self.token = token
        self.on_data_update = on_data_update
        self.socket: Any | None = None
        self._is_closing = False
        self._cleaning_up_socket = False
        self._reconnect_task: asyncio.Task[None] | None = None
        self._reconnect_interval = self._reconnect_interval_for_attempt(1)
        self._reconnect_warn_every = 12
        self._status_update_callback = status_update_callback
        self._status = "Not initialized"
        self._status_reason: str | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _ctx(self, device_id: str | None = None) -> str:
        """Build consistent log context."""
        base = (
            f"context_id={_log_identifier(self.context_id)} "
            f"location_id={_log_identifier(self.location_id)}"
        )
        if device_id:
            return f"{base} device_id={_log_identifier(device_id)}"
        return base

    def _reconnect_interval_for_attempt(self, attempt: int) -> int:
        """Return reconnect delay for the given attempt number."""
        if attempt <= 3:
            return 10
        if attempt <= 8:
            return 60
        return 300

    @property
    def websocket_url(self) -> str:
        """WebSocket base URL."""
        return self.WEBSOCKET_URL

    @staticmethod
    def _bearer_value(token: str | None) -> str:
        """Return normalized bearer token value."""
        normalized = (token or "").strip()
        if normalized.lower().startswith("bearer "):
            return normalized
        return f"Bearer {normalized}"

    @property
    def status(self) -> str:
        """Return current websocket status string."""
        return self._status

    @property
    def status_reason(self) -> str | None:
        """Return latest status reason if available."""
        return self._status_reason

    def _set_status(self, status: str, reason: str | None = None) -> None:
        """Update internal status and notify callback."""
        status_changed = status != self._status
        reason_changed = reason != self._status_reason
        self._status = status
        self._status_reason = reason

        if status_changed:
            if status == "Connected":
                _LOGGER.debug("WebSocket connected %s", self._ctx())
            elif status == "Disconnected":
                if reason and self._should_warn_disconnect(reason):
                    _LOGGER.info("WebSocket disconnected %s (%s)", self._ctx(), reason)
                elif reason:
                    _LOGGER.debug("WebSocket disconnected %s (%s)", self._ctx(), reason)
                else:
                    _LOGGER.info("WebSocket disconnected %s", self._ctx())
            else:
                if reason:
                    _LOGGER.debug(
                        "WebSocket status changed %s: %s (%s)",
                        self._ctx(),
                        status,
                        reason,
                    )
                else:
                    _LOGGER.debug("WebSocket status changed %s: %s", self._ctx(), status)
        elif reason_changed and reason:
            _LOGGER.debug("WebSocket status reason updated %s: %s", self._ctx(), reason)

        if self._status_update_callback:
            try:
                self._status_update_callback(status, reason)
            except Exception as err:
                _LOGGER.debug("Status callback failed %s: %s", self._ctx(), err)

    def _build_reason(self, data: Any) -> str | None:
        """Build a readable reason string from event payload."""
        if data is None:
            return None
        try:
            reason = str(data)
        except Exception:
            reason = repr(data)
        return reason or None

    @staticmethod
    def _should_warn_disconnect(reason: str | None) -> bool:
        """Return whether a disconnect reason should be warning-level."""
        if reason is None:
            return True
        if reason == "manual disconnect":
            return False
        transient_prefixes = (
            "connect timeout",
            "network error:",
            "connect exception:",
            "connect_error",
        )
        return not reason.startswith(transient_prefixes)

    def _on_event(self, data: Any) -> None:
        """Handle event payload from websocket."""
        if not self.is_connected():
            self._set_status("Connected", "event received")
        elif self._status != "Connected":
            self._set_status("Connected")

        device_id = data.get("data", {}).get("deviceId") if isinstance(data, dict) else None
        if isinstance(data, dict):
            event_type = data.get("type") or data.get("event") or "unknown"
            _LOGGER.debug(
                "WebSocket event received %s event_type=%s",
                self._ctx(device_id=device_id),
                event_type,
            )
        else:
            _LOGGER.debug(
                "WebSocket event received %s non-dict payload",
                self._ctx(device_id=device_id),
            )
        if isinstance(data, dict):
            try:
                self.on_data_update(data)
            except Exception as err:
                _LOGGER.error(
                    "Error in on_data_update callback %s: %s",
                    self._ctx(device_id=device_id),
                    err,
                    exc_info=True,
                )

    def _on_connect(self) -> None:
        """Handle successful connection."""
        self._stop_reconnect_loop()
        self._set_status("Connected")

    def _on_disconnect(self, reason: str | None = None) -> None:
        """Handle disconnected connection."""
        if self._is_closing:
            self._set_status("Disconnected", "manual disconnect")
            return
        if self._cleaning_up_socket:
            return
        self._set_status("Disconnected", reason)
        if not self._is_closing:
            self._start_reconnect_loop("disconnect event")
            _LOGGER.debug(
                "Reconnect requested after disconnect %s interval=%ss",
                self._ctx(),
                self._reconnect_interval,
            )

    def _start_reconnect_loop(self, reason: str | None = None) -> None:
        """Start reconnect loop if not already running."""
        if self._is_closing:
            return
        if self._reconnect_task and not self._reconnect_task.done():
            return

        self._reconnect_interval = self._reconnect_interval_for_attempt(1)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = self._loop
            if loop is None:
                _LOGGER.error(
                    "Cannot start reconnect loop: no event loop available %s",
                    self._ctx(),
                )
                return

        self._reconnect_task = loop.create_task(self._reconnect_loop())
        if reason:
            _LOGGER.debug(
                "Started reconnect loop %s (%s). interval=%ss, retries=infinite",
                self._ctx(),
                reason,
                self._reconnect_interval,
            )
        else:
            _LOGGER.debug(
                "Started reconnect loop %s. interval=%ss, retries=infinite",
                self._ctx(),
                self._reconnect_interval,
            )

    def _stop_reconnect_loop(self) -> None:
        """Stop reconnect loop."""
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        self._reconnect_task = None

    async def _reconnect_loop(self) -> None:
        """Reconnect with a short burst first, then slower retries."""
        attempt = 0
        while not self._is_closing:
            if self.is_connected():
                return

            attempt += 1
            _LOGGER.debug("WebSocket reconnect attempt %s started %s", attempt, self._ctx())
            success = await self.connect(from_reconnect_loop=True)
            if success:
                _LOGGER.debug("WebSocket reconnect attempt %s succeeded %s", attempt, self._ctx())
                return

            self._reconnect_interval = self._reconnect_interval_for_attempt(attempt + 1)
            if attempt % self._reconnect_warn_every == 0:
                _LOGGER.info(
                    "WebSocket reconnect attempt %s failed %s. Retrying in %s seconds",
                    attempt,
                    self._ctx(),
                    self._reconnect_interval,
                )
            else:
                _LOGGER.debug(
                    "WebSocket reconnect attempt %s failed %s. Retrying in %s seconds",
                    attempt,
                    self._ctx(),
                    self._reconnect_interval,
                )
            await asyncio.sleep(self._reconnect_interval)

    async def connect(self, from_reconnect_loop: bool = False) -> bool:
        """Connect to websocket server."""
        if self._is_closing:
            _LOGGER.debug("Skipping websocket connect during shutdown %s", self._ctx())
            return False

        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

        try:
            import socketio  # type: ignore[import-untyped]
        except ImportError:
            _LOGGER.error("python-socketio is not installed. WebSocket disabled %s.", self._ctx())
            self._set_status("Disconnected", "socketio missing")
            return False

        if self.is_connected():
            self._set_status("Connected")
            return True

        if self.socket is not None:
            self._cleaning_up_socket = True
            try:
                await asyncio.wait_for(self.socket.disconnect(), timeout=2)
            except Exception:
                pass
            finally:
                self._cleaning_up_socket = False
            self.socket = None

        self._set_status("Connecting")
        try:
            self.socket = socketio.AsyncClient(
                reconnection=False,
                logger=False,
                engineio_logger=logging.getLogger("engineio.client"),
            )

            async def connect() -> None:
                self._on_connect()

            async def disconnect(*args: Any) -> None:
                self._on_disconnect(self._build_reason(args[0] if args else None))

            async def message(data: Any) -> None:
                self._on_event(data)

            async def event(data: Any) -> None:
                self._on_event(data)

            async def catch_all(event: str, data: Any) -> None:
                if event not in ("connect", "disconnect", "message", "event", "connect_error"):
                    _LOGGER.debug("WebSocket event %s type=%s", self._ctx(), event)
                    self._on_event({"type": event, "payload": data})

            async def connect_error(data: Any) -> None:
                raw_reason = self._build_reason(data)
                reason = f"connect_error: {raw_reason}" if raw_reason else "connect_error"
                _LOGGER.debug("WebSocket connect_error %s: %s", self._ctx(), reason)
                self._on_disconnect(reason)

            self.socket.on("connect", connect)
            self.socket.on("disconnect", disconnect)
            self.socket.on("message", message)
            self.socket.on("event", event)
            self.socket.on("*", catch_all)
            self.socket.on("connect_error", connect_error)

            bearer_token = self._bearer_value(self.token)
            query = urlencode(
                {
                    "locationId": str(self.location_id),
                    "token": bearer_token,
                }
            )
            url = f"{self.websocket_url}?{query}"
            _LOGGER.debug("WebSocket connecting %s to %s", self._ctx(), self.websocket_url)
            await asyncio.wait_for(
                self.socket.connect(
                    url,
                    transports=["websocket"],
                    headers={"Authorization": bearer_token},
                ),
                timeout=10,
            )
            return True
        except TimeoutError:
            self.socket = None
            self._set_status("Disconnected", "connect timeout")
        except aiohttp.ClientError as err:
            self.socket = None
            self._set_status("Disconnected", f"network error: {err}")
        except Exception as err:
            self.socket = None
            self._set_status("Disconnected", f"connect exception: {err}")
            _LOGGER.error(
                "WebSocket connect failed %s: %s (%s)",
                self._ctx(),
                err,
                type(err).__name__,
            )

        if not from_reconnect_loop:
            self._start_reconnect_loop("connect failed")
        return False

    async def connect_or_raise(self) -> None:
        """Connect to the websocket server or raise a typed exception."""
        if not await self.connect():
            raise HomelyWebSocketError(
                f"Could not connect Homely websocket: {self.status_reason or self.status}"
            )

    async def disconnect(self) -> None:
        """Disconnect websocket and stop reconnecting."""
        self._is_closing = True
        self._stop_reconnect_loop()
        try:
            if self.socket is not None:
                try:
                    await asyncio.wait_for(self.socket.disconnect(), timeout=5)
                except Exception:
                    pass
                finally:
                    self.socket = None
        finally:
            self._set_status("Disconnected", "manual disconnect")

    async def close(self) -> None:
        """Alias for disconnect, matching common client-library conventions."""
        await self.disconnect()

    async def reconnect_with_token(self, token: str) -> None:
        """Update token and request reconnect if currently disconnected."""
        self.sync_token(token)

    def is_connected(self) -> bool:
        """Return True when the websocket transport looks alive."""
        try:
            return _socket_transport_is_connected(self.socket)
        except Exception:
            return False

    def reported_connection_status(self) -> str:
        """Return normalized status reported by the websocket client itself."""
        status = normalize_websocket_status(self.status)
        if status != "unknown" and not (
            status == "not_initialized" and self.is_connected()
        ):
            return status
        return "connected" if self.is_connected() else "disconnected"

    def connection_state(self) -> WebSocketConnectionState:
        """Return a normalized view of websocket health."""
        reported_status = self.reported_connection_status()
        connected = self.is_connected()

        if connected:
            effective_status = "connected"
        elif reported_status in {"connecting", "not_initialized"}:
            effective_status = reported_status
        elif reported_status == "unknown":
            effective_status = "disconnected"
        else:
            effective_status = "disconnected"

        return WebSocketConnectionState(
            connected=connected,
            reported_status=reported_status,
            effective_status=effective_status,
            reason=self.status_reason,
            status_mismatch=reported_status != effective_status,
        )

    def update_token(self, token: str, reconnect_if_disconnected: bool = False) -> None:
        """Update token used by next connect/reconnect attempt."""
        if not token:
            return
        if token != self.token:
            self.token = token
            _LOGGER.debug("WebSocket token updated %s", self._ctx())
        if reconnect_if_disconnected and not self.is_connected() and not self._is_closing:
            self._start_reconnect_loop("token changed while disconnected")

    def sync_token(self, token: str) -> str:
        """Update token and request reconnect only when the socket is actually down."""
        if not token:
            return "ignored_empty"

        reconnect_if_disconnected = not self.is_connected()
        self.update_token(
            token,
            reconnect_if_disconnected=reconnect_if_disconnected,
        )
        return (
            "reconnect_if_disconnected"
            if reconnect_if_disconnected
            else "no_reconnect"
        )

    def set_token(self, token: str, reconnect_if_disconnected: bool = False) -> None:
        """Alias for update_token, matching common client-library conventions."""
        self.update_token(token, reconnect_if_disconnected=reconnect_if_disconnected)

    def request_reconnect(self, reason: str = "manual request") -> None:
        """Start reconnect loop if disconnected."""
        if self._is_closing:
            return
        if self.is_connected():
            return
        self._start_reconnect_loop(reason)
