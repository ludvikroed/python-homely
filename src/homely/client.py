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


def _log_identifier(value: str | int | None) -> str | None:
    """Return a shortened identifier suitable for debug logs."""
    if value is None:
        return None

    text = str(value)
    if len(text) <= 8:
        return text
    return f"{text[:8]}..."


def auth_header_value(token: str | None) -> str:
    """Return normalized Authorization header value."""
    normalized = (token or "").strip()
    if normalized.lower().startswith("bearer "):
        return normalized
    return f"Bearer {normalized}"


def _response_preview(payload: Any) -> str:
    """Return a short safe preview of a response payload for exceptions."""
    text = repr(payload)
    if len(text) <= 200:
        return text
    return f"{text[:200]}..."


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
        response, status = await self._fetch_token_payload(username, password)
        if response is not None:
            try:
                return TokenResponse.from_dict(response)
            except (KeyError, TypeError, ValueError) as err:
                raise HomelyResponseError(
                    "Homely authentication response missing required fields",
                    status=status,
                    body=_response_preview(response),
                ) from err
        if status in (400, 401, 403):
            raise HomelyAuthError("Invalid Homely username or password")
        if status in (200, 201):
            raise HomelyResponseError(
                "Homely authentication response could not be parsed",
                status=status,
            )
        raise HomelyConnectionError("Could not connect to Homely")

    async def _fetch_token_payload(
        self,
        username: str,
        password: str,
    ) -> tuple[dict[str, Any] | None, int | None]:
        """Fetch access token payload and include HTTP status when available."""
        url = f"{self._base_url}oauth/token"
        payload = {
            "username": username,
            "password": password,
        }

        try:
            async with self._session.post(url, json=payload, timeout=self._timeout) as response:
                if response.status in (200, 201):
                    try:
                        parsed = await response.json()
                    except (aiohttp.ContentTypeError, TypeError, ValueError) as err:
                        _LOGGER.debug(
                            "Token fetch returned invalid JSON status=%s: %s",
                            response.status,
                            err,
                        )
                        return None, response.status
                    if not isinstance(parsed, dict):
                        _LOGGER.debug(
                            "Token fetch returned unexpected payload type status=%s payload_type=%s",
                            response.status,
                            type(parsed).__name__,
                        )
                        return None, response.status
                    _LOGGER.debug("Token fetch successful")
                    return parsed, response.status

                _LOGGER.debug("Token fetch failed with status=%s", response.status)
                return None, response.status
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Token fetch network error: %s", err)
            return None, None

    async def fetch_token_with_reason(
        self,
        username: str,
        password: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Fetch access token and return optional reason key on failure."""
        response, status = await self._fetch_token_payload(username, password)
        if response is not None:
            return response, None
        if status in (400, 401, 403):
            return None, "invalid_auth"
        return None, "cannot_connect"

    async def fetch_token(
        self,
        username: str,
        password: str,
    ) -> dict[str, Any] | None:
        """Fetch access token from API."""
        response, _reason = await self.fetch_token_with_reason(username, password)
        return response

    async def _fetch_refresh_token_payload(
        self,
        refresh_token: str,
    ) -> tuple[dict[str, Any] | None, int | None]:
        """Refresh access token payload and include HTTP status when available."""
        url = f"{self._base_url}oauth/refresh-token"
        payload = {
            "refresh_token": refresh_token,
        }

        try:
            async with self._session.post(url, json=payload, timeout=self._timeout) as response:
                if response.status in (200, 201):
                    try:
                        parsed = await response.json()
                    except (aiohttp.ContentTypeError, TypeError, ValueError) as err:
                        _LOGGER.debug(
                            "Token refresh returned invalid JSON status=%s: %s",
                            response.status,
                            err,
                        )
                        return None, response.status
                    if not isinstance(parsed, dict):
                        _LOGGER.debug(
                            "Token refresh returned unexpected payload type status=%s payload_type=%s",
                            response.status,
                            type(parsed).__name__,
                        )
                        return None, response.status
                    _LOGGER.debug("Token refresh successful")
                    return parsed, response.status
                _LOGGER.debug("Token refresh failed with status=%s", response.status)
                return None, response.status
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Token refresh network error: %s", err)
            return None, None

    async def fetch_refresh_token(self, refresh_token: str) -> dict[str, Any] | None:
        """Refresh access token using refresh token."""
        response, _status = await self._fetch_refresh_token_payload(refresh_token)
        return response

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """Refresh access token and return a typed token response."""
        response, status = await self._fetch_refresh_token_payload(refresh_token)
        if response is not None:
            try:
                return TokenResponse.from_dict(response)
            except (KeyError, TypeError, ValueError) as err:
                raise HomelyResponseError(
                    "Homely refresh response missing required fields",
                    status=status,
                    body=_response_preview(response),
                ) from err
        if status in (400, 401, 403):
            raise HomelyAuthError("Homely rejected the supplied refresh token")
        if status in (200, 201):
            raise HomelyResponseError(
                "Homely refresh response could not be parsed",
                status=status,
            )
        raise HomelyConnectionError("Could not refresh Homely access token")

    async def _get_locations_payload(
        self,
        token: str,
    ) -> tuple[list[dict[str, Any]] | None, int | None]:
        """Get locations payload and include HTTP status when available."""
        url = f"{self._base_url}locations"
        headers = {"Authorization": auth_header_value(token)}

        try:
            async with self._session.get(url, headers=headers, timeout=self._timeout) as response:
                if response.status == 200:
                    try:
                        parsed = await response.json()
                    except (aiohttp.ContentTypeError, TypeError, ValueError) as err:
                        _LOGGER.debug(
                            "Locations fetch returned invalid JSON status=%s: %s",
                            response.status,
                            err,
                        )
                        return None, response.status
                    if not isinstance(parsed, list):
                        _LOGGER.debug(
                            "Locations fetch returned unexpected payload type status=%s payload_type=%s",
                            response.status,
                            type(parsed).__name__,
                        )
                        return None, response.status
                    _LOGGER.debug("Locations fetch successful")
                    return parsed, response.status
                _LOGGER.debug("Locations fetch failed with status=%s", response.status)
                return None, response.status
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Locations fetch network error: %s", err)
            return None, None

    async def get_locations(self, token: str) -> list[dict[str, Any]] | None:
        """Get locations from API."""
        locations, _status = await self._get_locations_payload(token)
        return locations

    async def get_locations_or_raise(self, token: str) -> list[dict[str, Any]]:
        """Get locations from API or raise a typed exception."""
        locations, status = await self._get_locations_payload(token)
        if locations is not None:
            return locations
        if status in (401, 403):
            raise HomelyAuthError("Homely rejected the supplied access token")
        if status == 200:
            raise HomelyResponseError(
                "Homely locations response could not be parsed",
                status=status,
            )
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
                    try:
                        parsed = await response.json()
                    except (aiohttp.ContentTypeError, TypeError, ValueError) as err:
                        _LOGGER.debug(
                            "Location data fetch returned invalid JSON status=%s location_id=%s: %s",
                            response.status,
                            _log_identifier(location_id),
                            err,
                        )
                        return None, response.status
                    if not isinstance(parsed, dict):
                        _LOGGER.debug(
                            "Location data fetch returned unexpected payload type status=%s location_id=%s payload_type=%s",
                            response.status,
                            _log_identifier(location_id),
                            type(parsed).__name__,
                        )
                        return None, response.status
                    return parsed, response.status
                _LOGGER.debug(
                    "Location data fetch failed with status=%s location_id=%s",
                    response.status,
                    _log_identifier(location_id),
                )
                return None, response.status
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug(
                "Location data fetch network error location_id=%s: %s",
                _log_identifier(location_id),
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
