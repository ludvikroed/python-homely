"""Tests for the public python-homely SDK package."""
from __future__ import annotations

import aiohttp

from homely import (
    HomelyAuthError,
    HomelyClient,
    HomelyConnectionError,
    HomelyResponseError,
    HomelyWebSocket,
    HomelyWebSocketError,
    TokenResponse,
    __version__,
    auth_header_value,
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
    ) -> None:
        self.status = status
        self._json_data = json_data
        self._text_data = text_data
        self._json_exc = json_exc

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
    assert __version__ == "0.1.1"


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


async def test_authenticate_raises_auth_error():
    """Authentication failures should raise HomelyAuthError."""
    client = HomelyClient(_FakeSession(post_response=_FakeResponse(status=401)))

    try:
        await client.authenticate("user", "pass")
    except HomelyAuthError:
        pass
    else:
        raise AssertionError("Expected HomelyAuthError")


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
