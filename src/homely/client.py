"""Async Homely API client."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .exceptions import (
    HomelyAuthError,
    HomelyConnectionError,
    HomelyResponseError,
)
from .models import TokenResponse

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://sdk.iotiliti.cloud/homely/"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)


def auth_header_value(token: str | None) -> str:
    """Return normalized Authorization header value."""
    normalized = (token or "").strip()
    if normalized.lower().startswith("bearer "):
        return normalized
    return f"Bearer {normalized}"


class HomelyClient:
    """Small reusable async client for the Homely cloud API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        base_url: str = BASE_URL,
        timeout: aiohttp.ClientTimeout = REQUEST_TIMEOUT,
    ) -> None:
        """Initialize the client with a caller-managed aiohttp session."""
        self._session = session
        self._base_url = base_url
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        """Return the configured API base URL."""
        return self._base_url

    @property
    def timeout(self) -> aiohttp.ClientTimeout:
        """Return the configured request timeout."""
        return self._timeout

    async def authenticate(
        self,
        username: str,
        password: str,
    ) -> TokenResponse:
        """Authenticate and return a typed token response.

        Raises a typed SDK exception on failure.
        """
        response, reason = await self.fetch_token_with_reason(username, password)
        if response:
            return TokenResponse.from_dict(response)
        if reason == "invalid_auth":
            raise HomelyAuthError("Invalid Homely username or password")
        raise HomelyConnectionError("Could not connect to Homely")

    async def fetch_token_with_reason(
        self,
        username: str,
        password: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Fetch access token and return optional reason key on failure."""
        url = f"{self._base_url}oauth/token"
        payload = {
            "username": username,
            "password": password,
        }

        try:
            async with self._session.post(url, json=payload, timeout=self._timeout) as response:
                if response.status in (200, 201):
                    _LOGGER.debug("Token fetch successful")
                    return await response.json(), None

                if response.status in (400, 401, 403):
                    _LOGGER.debug("Token fetch rejected with status=%s", response.status)
                    return None, "invalid_auth"

                _LOGGER.warning("Token fetch failed with status=%s", response.status)
                return None, "cannot_connect"
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.warning("Token fetch network error: %s", err)
            return None, "cannot_connect"

    async def fetch_token(
        self,
        username: str,
        password: str,
    ) -> dict[str, Any] | None:
        """Fetch access token from API."""
        response, _reason = await self.fetch_token_with_reason(username, password)
        return response

    async def fetch_refresh_token(self, refresh_token: str) -> dict[str, Any] | None:
        """Refresh access token using refresh token."""
        url = f"{self._base_url}oauth/refresh-token"
        payload = {
            "refresh_token": refresh_token,
        }

        try:
            async with self._session.post(url, json=payload, timeout=self._timeout) as response:
                if response.status in (200, 201):
                    _LOGGER.debug("Token refresh successful")
                    return await response.json()
                _LOGGER.debug("Token refresh failed with status=%s", response.status)
                return None
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Token refresh network error: %s", err)
            return None

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """Refresh access token and return a typed token response."""
        response = await self.fetch_refresh_token(refresh_token)
        if response:
            return TokenResponse.from_dict(response)
        raise HomelyConnectionError("Could not refresh Homely access token")

    async def get_locations(self, token: str) -> list[dict[str, Any]] | None:
        """Get locations from API."""
        url = f"{self._base_url}locations"
        headers = {"Authorization": auth_header_value(token)}

        try:
            async with self._session.get(url, headers=headers, timeout=self._timeout) as response:
                if response.status == 200:
                    _LOGGER.debug("Locations fetch successful")
                    return await response.json()
                _LOGGER.debug("Locations fetch failed with status=%s", response.status)
                return None
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Locations fetch network error: %s", err)
            return None

    async def get_locations_or_raise(self, token: str) -> list[dict[str, Any]]:
        """Get locations from API or raise a typed exception."""
        locations = await self.get_locations(token)
        if locations is not None:
            return locations
        raise HomelyConnectionError("Could not fetch Homely locations")

    async def get_home_data(
        self,
        token: str,
        location_id: str | int,
    ) -> dict[str, Any] | None:
        """Get location data from API."""
        data, _status = await self.get_home_data_with_status(token, location_id)
        return data

    async def get_home_data_with_status(
        self,
        token: str,
        location_id: str | int,
    ) -> tuple[dict[str, Any] | None, int | None]:
        """Get location data from API and include HTTP status when available."""
        url = f"{self._base_url}home/{location_id}"
        headers = {"Authorization": auth_header_value(token)}

        try:
            async with self._session.get(url, headers=headers, timeout=self._timeout) as response:
                if response.status == 200:
                    return await response.json(), response.status
                body = await response.text()
                body_preview = body.replace("\n", " ")[:200]
                _LOGGER.debug(
                    "Location data fetch failed with status=%s location_id=%s body_preview=%r",
                    response.status,
                    location_id,
                    body_preview,
                )
                return None, response.status
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug(
                "Location data fetch network error location_id=%s: %s",
                location_id,
                err,
            )
            return None, None

    async def get_home_data_or_raise(
        self,
        token: str,
        location_id: str | int,
    ) -> dict[str, Any]:
        """Get location data from API or raise a typed exception."""
        data, status = await self.get_home_data_with_status(token, location_id)
        if data is not None:
            return data
        if status in (401, 403):
            raise HomelyAuthError("Homely rejected the supplied access token")
        raise HomelyResponseError(
            "Could not fetch Homely location data",
            status=status,
        )
