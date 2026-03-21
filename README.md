# Python-homely

Async Python client for the Homely cloud API and realtime websocket updates.

This package was created for the Homely Home Assistant integration, but it is framework-independent and can be used in any Python project that needs to talk to Homely.

## Features

- Login and token refresh
- Location and home-data fetches
- Realtime websocket updates
- Typed exceptions
- Async API built on `aiohttp`

## Installation

```bash
python3 -m pip install python-homely
```

## Quick Start

```python
import aiohttp
from homely import HomelyClient


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        client = HomelyClient(session)

        token = await client.authenticate("user@example.com", "password")
        locations = await client.get_locations_or_raise(token.access_token)
        location_id = locations[0]["locationId"]

        data = await client.get_home_data_or_raise(token.access_token, location_id)
        print(data["name"])
```

## Websocket Example

```python
import aiohttp
from homely import HomelyClient, HomelyWebSocket


async def on_update(event: dict) -> None:
    print(event)


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        client = HomelyClient(session)
        token = await client.authenticate("user@example.com", "password")
        locations = await client.get_locations_or_raise(token.access_token)
        location_id = locations[0]["locationId"]

        websocket = HomelyWebSocket(
            location_id=location_id,
            token=token.access_token,
            on_data_update=on_update,
            context_id="example",
        )

        await websocket.connect_or_raise()
```

## Main API

- `authenticate(username, password) -> TokenResponse`
- `refresh_access_token(refresh_token) -> TokenResponse`
- `fetch_token_details(username, password) -> TokenEndpointResult`
- `fetch_refresh_token_details(refresh_token) -> TokenEndpointResult`
- `get_locations_or_raise(token) -> list[dict]`
- `get_home_data_or_raise(token, location_id) -> dict`
- `HomelyWebSocket(...).connect_or_raise()`

Legacy compatibility helpers remain available:

- `fetch_token_with_reason(username, password) -> tuple[dict | None, str | None]`
- `fetch_token(username, password) -> dict | None`
- `fetch_refresh_token(refresh_token) -> dict | None`

Main exports:

- `HomelyClient`
- `HomelyWebSocket`
- `TokenEndpointResult`
- `TokenResponse`
- `HomelyConnectionError`
- `HomelyAuthError`
- `HomelyResponseError`
- `HomelyWebSocketError`

## Exceptions

- `HomelyConnectionError`: network or service unavailable
- `HomelyAuthError`: invalid credentials or rejected token
- `HomelyResponseError`: unexpected response or HTTP failure
  Carries `status` and `body_preview` when available.
- `HomelyWebSocketError`: websocket could not be established

## Token Diagnostics

If you need more than success/failure, use the detailed token helpers:

```python
result = await client.fetch_refresh_token_details(refresh_token)
if result.ok:
    print(result.token.access_token)
else:
    print(result.reason, result.status, result.detail, result.body_preview)
```

`TokenEndpointResult.reason` can distinguish between invalid credentials, invalid refresh
tokens, network errors, timeouts, malformed JSON, malformed payloads, empty responses, and
unexpected HTTP failures.

## Websocket Note

Refreshing an access token does not require forcing an already-connected websocket to reconnect.
The websocket token only matters when a new websocket connection is established or re-established.

## License

MIT. See [LICENSE](LICENSE).


⭐ If you find this package useful, please consider giving it a star on [GitHub](https://github.com/ludvikroed/python-homely)! ⭐
