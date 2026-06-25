"""Tests for the public python-homely SDK package."""
from __future__ import annotations

from types import SimpleNamespace

import aiohttp
import pytest

from homely import (
    WEBSOCKET_STATUS_OPTIONS,
    HomelyAuthError,
    HomelyClient,
    HomelyConnectionError,
    HomelyResponseError,
    HomelyWebSocket,
    HomelyWebSocketError,
    TokenEndpointResult,
    TokenResponse,
    __version__,
    auth_header_value,
    normalize_websocket_status,
)


class _FakeResponse:
    """Simple async HTTP response stub."""

    def __init__(
        self,
        *,
        status: int,
        json_data=None,
        text_data: str = "",
        json_exc: Exception | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self._json_data = json_data
        self._text_data = text_data
        self._json_exc = json_exc
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._json_data

    async def text(self):
        return self._text_data


class _FakeSession:
    """Simple aiohttp client stub."""

    def __init__(
        self,
        *,
        post_response=None,
        get_response=None,
        post_exc=None,
        get_exc=None,
    ) -> None:
        self._post_response = post_response
        self._get_response = get_response
        self._post_exc = post_exc
        self._get_exc = get_exc

    def post(self, *args, **kwargs):
        if self._post_exc is not None:
            raise self._post_exc
        return self._post_response

    def get(self, *args, **kwargs):
        if self._get_exc is not None:
            raise self._get_exc
        return self._get_response


class _FakeAsyncCallable:
    """Simple async callable test helper."""

    def __init__(self, result):
        self._result = result

    async def __call__(self, *args, **kwargs):
        return self._result


async def test_sdk_exports_public_symbols():
    """The SDK should expose a clean public surface."""
    assert auth_header_value("token") == "Bearer token"
    assert __version__ == "0.1.9"


async def test_authenticate_returns_typed_token():
    """Authentication should return a typed token model."""
    client = HomelyClient(
        _FakeSession(
            post_response=_FakeResponse(
                status=200,
                json_data={
                    "access_token": "token",
                    "refresh_token": "refresh",
                    "expires_in": "120",
                },
            )
        )
    )

    response = await client.authenticate("user", "pass")

    assert response == TokenResponse(
        access_token="token",
        refresh_token="refresh",
        expires_in=120,
        raw={
            "access_token": "token",
            "refresh_token": "refresh",
            "expires_in": "120",
        },
    )


async def test_fetch_token_details_returns_typed_result():
    """Detailed token fetches should preserve both token and metadata."""
    client = HomelyClient(
        _FakeSession(
            post_response=_FakeResponse(
                status=200,
                json_data={
                    "access_token": "token",
                    "refresh_token": "refresh",
                    "expires_in": 1800,
                },
            )
        )
    )

    result = await client.fetch_token_details("user", "pass")

    assert result == TokenEndpointResult(
        token=TokenResponse(
            access_token="token",
            refresh_token="refresh",
            expires_in=1800,
            raw={
                "access_token": "token",
                "refresh_token": "refresh",
                "expires_in": 1800,
            },
        ),
        status=200,
    )
    assert result.ok is True
    assert result.raw == {
        "access_token": "token",
        "refresh_token": "refresh",
        "expires_in": 1800,
    }


async def test_fetch_token_details_returns_invalid_auth_reason():
    """Detailed token fetches should classify auth failures explicitly."""
    client = HomelyClient(
        _FakeSession(
            post_response=_FakeResponse(status=401, text_data='{"error":"unauthorized"}')
        )
    )

    result = await client.fetch_token_details("user", "pass")

    assert result.ok is False
    assert result.reason == "invalid_auth"
    assert result.status == 401
    assert result.body_preview == '{"error":"unauthorized"}'


async def test_fetch_token_details_returns_timeout_reason():
    """Detailed token fetches should preserve timeout classification."""
    client = HomelyClient(_FakeSession(post_exc=TimeoutError()))

    result = await client.fetch_token_details("user", "pass")

    assert result.reason == "timeout"
    assert result.detail == "TimeoutError"


async def test_fetch_token_with_reason_remains_backward_compatible():
    """Legacy coarse token reasons should still be preserved."""
    client = HomelyClient(
        _FakeSession(
            post_response=_FakeResponse(status=200, json_exc=ValueError("bad json"))
        )
    )

    response, reason = await client.fetch_token_with_reason("user", "pass")

    assert response is None
    assert reason == "cannot_connect"


async def test_authenticate_raises_auth_error():
    """Authentication failures should raise HomelyAuthError."""
    client = HomelyClient(_FakeSession(post_response=_FakeResponse(status=401)))

    try:
        await client.authenticate("user", "pass")
    except HomelyAuthError:
        pass
    else:
        raise AssertionError("Expected HomelyAuthError")


async def test_authenticate_raises_response_error_with_body_preview_on_invalid_json():
    """Malformed successful auth payloads should include a short body preview."""
    client = HomelyClient(
        _FakeSession(
            post_response=_FakeResponse(
                status=200,
                text_data="not-json",
                json_exc=ValueError("bad json"),
            )
        )
    )

    with pytest.raises(HomelyResponseError) as err_info:
        await client.authenticate("user", "pass")

    assert err_info.value.status == 200
    assert err_info.value.body_preview == "not-json"
    assert err_info.value.body == "not-json"


async def test_refresh_access_token_raises_connection_error_on_timeout():
    """Refresh failures should raise HomelyConnectionError."""
    client = HomelyClient(_FakeSession(post_exc=TimeoutError()))

    try:
        await client.refresh_access_token("refresh-token")
    except HomelyConnectionError:
        pass
    else:
        raise AssertionError("Expected HomelyConnectionError")


async def test_refresh_access_token_raises_auth_error_on_expired_refresh_token():
    """Refresh auth failures should surface as HomelyAuthError."""
    client = HomelyClient(_FakeSession(post_response=_FakeResponse(status=400)))

    try:
        await client.refresh_access_token("refresh-token")
    except HomelyAuthError:
        pass
    else:
        raise AssertionError("Expected HomelyAuthError")


async def test_fetch_refresh_token_details_returns_http_error_with_preview():
    """Detailed refresh fetches should include status and body previews."""
    client = HomelyClient(
        _FakeSession(post_response=_FakeResponse(status=503, text_data="upstream down"))
    )

    result = await client.fetch_refresh_token_details("refresh-token")

    assert result.reason == "http_error"
    assert result.status == 503
    assert result.body_preview == "upstream down"


async def test_fetch_refresh_token_details_returns_invalid_payload_for_non_dict_success():
    """Detailed refresh fetches should reject non-dict success payloads explicitly."""
    client = HomelyClient(
        _FakeSession(post_response=_FakeResponse(status=200, json_data=["bad-payload"]))
    )

    result = await client.fetch_refresh_token_details("refresh-token")

    assert result.token is None
    assert result.reason == "invalid_payload"
    assert result.status == 200
    assert result.detail == "payload_type=list"
    assert result.body_preview == "['bad-payload']"


async def test_fetch_refresh_token_wrapper_remains_backward_compatible():
    """The legacy refresh wrapper should still return the raw payload on success."""
    client = HomelyClient(
        _FakeSession(
            post_response=_FakeResponse(
                status=200,
                json_data={
                    "access_token": "token",
                    "refresh_token": "refresh",
                    "expires_in": 120,
                },
            )
        )
    )

    response = await client.fetch_refresh_token("refresh-token")

    assert response == {
        "access_token": "token",
        "refresh_token": "refresh",
        "expires_in": 120,
    }


async def test_refresh_access_token_raises_response_error_with_preview():
    """Refresh HTTP failures should surface response metadata for callers."""
    client = HomelyClient(
        _FakeSession(post_response=_FakeResponse(status=503, text_data="upstream down"))
    )

    with pytest.raises(HomelyResponseError) as err_info:
        await client.refresh_access_token("refresh-token")

    assert err_info.value.status == 503
    assert err_info.value.body_preview == "upstream down"
    assert err_info.value.body == "upstream down"


async def test_response_error_preserves_body_and_preview_separately():
    """Response errors should keep body and body_preview as separate fields."""
    err = HomelyResponseError(
        "bad response",
        status=502,
        body="full body",
        body_preview="trimmed preview",
    )

    assert err.status == 502
    assert err.body == "full body"
    assert err.body_preview == "trimmed preview"


async def test_response_error_uses_body_as_preview_when_preview_is_missing():
    """Response errors should keep legacy body-only construction working."""
    err = HomelyResponseError(
        "bad response",
        status=502,
        body="full body",
    )

    assert err.status == 502
    assert err.body == "full body"
    assert err.body_preview == "full body"


async def test_get_locations_or_raise_raises_connection_error():
    """Location lookup failures should raise HomelyConnectionError."""
    client = HomelyClient(_FakeSession(get_exc=aiohttp.ClientError("boom")))

    try:
        await client.get_locations_or_raise("token")
    except HomelyConnectionError:
        pass
    else:
        raise AssertionError("Expected HomelyConnectionError")


async def test_get_locations_or_raise_raises_auth_error_on_unauthorized():
    """Unauthorized location lookups should raise HomelyAuthError."""
    client = HomelyClient(_FakeSession(get_response=_FakeResponse(status=401)))

    try:
        await client.get_locations_or_raise("token")
    except HomelyAuthError:
        pass
    else:
        raise AssertionError("Expected HomelyAuthError")


async def test_get_home_data_or_raise_raises_response_error():
    """Unexpected data fetch failures should carry response metadata."""
    client = HomelyClient(
        _FakeSession(
            get_response=_FakeResponse(status=500, text_data="server error")
        )
    )

    try:
        await client.get_home_data_or_raise("token", "loc-1")
    except HomelyResponseError as err:
        assert err.status == 500
    else:
        raise AssertionError("Expected HomelyResponseError")


async def test_authenticate_raises_response_error_on_malformed_success_payload():
    """Malformed successful auth responses should raise HomelyResponseError."""
    client = HomelyClient(
        _FakeSession(
            post_response=_FakeResponse(
                status=200,
                json_data={"refresh_token": "refresh"},
            )
        )
    )

    try:
        await client.authenticate("user", "pass")
    except HomelyResponseError as err:
        assert err.status == 200
    else:
        raise AssertionError("Expected HomelyResponseError")


async def test_get_locations_or_raise_raises_response_error_on_malformed_success_payload():
    """Malformed successful location responses should raise HomelyResponseError."""
    client = HomelyClient(
        _FakeSession(
            get_response=_FakeResponse(
                status=200,
                json_data={"bad": "payload"},
            )
        )
    )

    try:
        await client.get_locations_or_raise("token")
    except HomelyResponseError as err:
        assert err.status == 200
    else:
        raise AssertionError("Expected HomelyResponseError")


async def test_get_home_data_or_raise_raises_response_error_on_invalid_json():
    """Malformed successful location payloads should raise HomelyResponseError."""
    client = HomelyClient(
        _FakeSession(
            get_response=_FakeResponse(status=200, json_exc=ValueError("bad json"))
        )
    )

    try:
        await client.get_home_data_or_raise("token", "loc-1")
    except HomelyResponseError as err:
        assert err.status == 200
    else:
        raise AssertionError("Expected HomelyResponseError")


async def test_websocket_public_aliases_cover_package_api():
    """The websocket client should expose package-friendly aliases."""
    ws = HomelyWebSocket(
        location_id="11111111-2222-3333-4444-555555555555",
        token="token",
        on_data_update=lambda _data: None,
        context_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )

    assert ws.context_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert ws.entry_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    ws.set_token("new-token")
    assert ws.token == "new-token"
    assert ws._ctx("99999999-8888-7777-6666-555555555555") == (
        "context_id=aaaaaaaa... "
        "location_id=11111111... "
        "device_id=99999999..."
    )

    assert normalize_websocket_status(" Connected ") == "connected"
    assert tuple(WEBSOCKET_STATUS_OPTIONS) == (
        "not_initialized",
        "connecting",
        "connected",
        "disconnected",
        "unknown",
    )


async def test_websocket_connection_state_uses_engineio_transport_health():
    """Connection state should treat a live Engine.IO transport as connected."""
    ws = HomelyWebSocket(
        location_id="loc-1",
        token="token",
        on_data_update=lambda _data: None,
    )
    ws._status = "Connected"
    ws.socket = SimpleNamespace(
        connected=False,
        eio=SimpleNamespace(state="connected"),
    )

    state = ws.connection_state()

    assert state.connected is True
    assert state.reported_status == "connected"
    assert state.effective_status == "connected"
    assert state.status_mismatch is False


async def test_connect_keeps_engineio_logger_disabled(monkeypatch):
    """SECURITY: the Engine.IO logger must stay off.

    When enabled it logs the full connection URL, which carries the bearer
    token in the query string (?token=Bearer <access_token>), leaking it to
    the consuming application's logs.
    """
    import socketio

    captured: dict[str, object] = {}

    class _FakeSocket:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def on(self, *args: object, **kwargs: object) -> None:
            return None

        async def connect(self, *args: object, **kwargs: object) -> None:
            return None

    # connect() does a local `import socketio`, so patch the real module.
    monkeypatch.setattr(socketio, "AsyncClient", _FakeSocket)

    ws = HomelyWebSocket(
        location_id="loc-1",
        token="super-secret-token",
        on_data_update=lambda _data: None,
    )
    await ws.connect()

    assert captured.get("engineio_logger") is False
    assert captured.get("logger") is False


async def test_websocket_sync_token_only_reconnects_when_transport_is_down():
    """Token sync should not nudge healthy sockets, but should reconnect dead ones."""
    ws = HomelyWebSocket(
        location_id="loc-1",
        token="old-token",
        on_data_update=lambda _data: None,
    )

    ws.socket = SimpleNamespace(connected=True)
    assert ws.sync_token("fresh-token") == "no_reconnect"
    assert ws.token == "fresh-token"

    ws.socket = SimpleNamespace(connected=False, eio=SimpleNamespace(state="closed"))
    with pytest.MonkeyPatch.context() as monkeypatch:
        reconnect_reasons: list[str | None] = []
        monkeypatch.setattr(
            ws,
            "_start_reconnect_loop",
            lambda reason=None: reconnect_reasons.append(reason),
        )
        result = ws.sync_token("newer-token")

    assert result == "reconnect_if_disconnected"
    assert reconnect_reasons == ["token changed while disconnected"]


async def test_websocket_connect_or_raise_uses_typed_exception():
    """Websocket connection failures should raise a typed exception."""
    ws = HomelyWebSocket(
        location_id="loc-1",
        token="token",
        on_data_update=lambda _data: None,
    )
    ws.connect = _FakeAsyncCallable(False)
    ws._status_reason = "connect timeout"

    try:
        await ws.connect_or_raise()
    except HomelyWebSocketError:
        pass
    else:
        raise AssertionError("Expected HomelyWebSocketError")
