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
- `get_locations_or_raise(token) -> list[dict]`
- `get_home_data_or_raise(token, location_id) -> dict`
- `HomelyWebSocket(...).connect_or_raise()`

Main exports:

- `HomelyClient`
- `HomelyWebSocket`
- `TokenResponse`
- `HomelyConnectionError`
- `HomelyAuthError`
- `HomelyResponseError`
- `HomelyWebSocketError`

## Exceptions

- `HomelyConnectionError`: network or service unavailable
- `HomelyAuthError`: invalid credentials or rejected token
- `HomelyResponseError`: unexpected response or HTTP failure
- `HomelyWebSocketError`: websocket could not be established

## License

MIT. See [LICENSE](LICENSE).
