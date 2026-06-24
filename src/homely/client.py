"""Async Homely API client."""
from __future__ import annotations

import logging
from typing import Any, NoReturn

import aiohttp

from .exceptions import (
    HomelyAuthError,
    HomelyConnectionError,
    HomelyResponseError,
)
from .models import TokenEndpointResult, TokenFailureReason, TokenResponse

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


def _text_preview(text: str | None) -> str | None:
    """Return a trimmed short preview of response text."""
    if text is None:
        return None

    preview = text.strip()
    if not preview:
        return None
    if len(preview) <= 200:
        return preview
    return f"{preview[:200]}..."


def _error_detail(err: BaseException) -> str:
    """Return a compact detail string for logs and typed results."""
    detail = str(err).strip()
    if detail:
        return detail
    return err.__class__.__name__


def _coarse_token_reason(reason: TokenFailureReason | None) -> str | None:
    """Map detailed token failure reasons to the legacy coarse reason set."""
    if reason == "invalid_auth":
        return "invalid_auth"
    if reason is None:
        return None
    return "cannot_connect"


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
        result = await self.fetch_token_details(username, password)
        if result.token is not None:
            return result.token
        self._raise_token_endpoint_failure(
            result,
            invalid_reason="invalid_auth",
            invalid_message="Invalid Homely username or password",
            connection_message="Could not connect to Homely",
            malformed_message="Homely authentication response could not be parsed",
            response_message="Homely authentication failed",
        )

    async def _fetch_token_payload(
        self,
        username: str,
        password: str,
    ) -> tuple[dict[str, Any] | None, int | None]:
        """Fetch access token payload and include HTTP status when available."""
        result = await self.fetch_token_details(username, password)
        return result.raw, result.status

    async def fetch_token_details(
        self,
        username: str,
        password: str,
    ) -> TokenEndpointResult:
        """Fetch a token and return a detailed typed result."""
        payload = {
            "username": username,
            "password": password,
        }
        return await self._post_token_endpoint(
            endpoint="oauth/token",
            payload=payload,
            invalid_reason="invalid_auth",
            action="Token fetch",
        )

    async def fetch_token_with_reason(
        self,
        username: str,
        password: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Fetch access token and return optional reason key on failure."""
        result = await self.fetch_token_details(username, password)
        if result.raw is not None:
            return result.raw, None
        return None, _coarse_token_reason(result.reason)

    async def fetch_token(
        self,
        username: str,
        password: str,
    ) -> dict[str, Any] | None:
        """Fetch access token from API."""
        result = await self.fetch_token_details(username, password)
        return result.raw

    async def _fetch_refresh_token_payload(
        self,
        refresh_token: str,
    ) -> tuple[dict[str, Any] | None, int | None]:
        """Refresh access token payload and include HTTP status when available."""
        result = await self.fetch_refresh_token_details(refresh_token)
        return result.raw, result.status

    async def fetch_refresh_token_details(
        self,
        refresh_token: str,
    ) -> TokenEndpointResult:
        """Refresh a token and return a detailed typed result."""
        payload = {
            "refresh_token": refresh_token,
        }
        return await self._post_token_endpoint(
            endpoint="oauth/refresh-token",
            payload=payload,
            invalid_reason="invalid_refresh_token",
            action="Token refresh",
            extra_headers={"X-Forwarded-For": "0.0.0.0"},
        )

    async def fetch_refresh_token(self, refresh_token: str) -> dict[str, Any] | None:
        """Refresh access token using refresh token."""
        result = await self.fetch_refresh_token_details(refresh_token)
        return result.raw

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """Refresh access token and return a typed token response."""
        result = await self.fetch_refresh_token_details(refresh_token)
        if result.token is not None:
            return result.token
        self._raise_token_endpoint_failure(
            result,
            invalid_reason="invalid_refresh_token",
            invalid_message="Homely rejected the supplied refresh token",
            connection_message="Could not refresh Homely access token",
            malformed_message="Homely refresh response could not be parsed",
            response_message="Homely refresh request failed",
        )

    async def _post_token_endpoint(
        self,
        *,
        endpoint: str,
        payload: dict[str, Any],
        invalid_reason: TokenFailureReason,
        action: str,
        extra_headers: dict[str, str] | None = None,
    ) -> TokenEndpointResult:
        """Post to a token endpoint and return a detailed typed result."""
        url = f"{self._base_url}{endpoint}"

        try:
            async with self._session.post(
                url, json=payload, headers=extra_headers, timeout=self._timeout
            ) as response:
                body_preview = await self._response_text_preview(response)
                if response.status in (200, 201):
                    try:
                        parsed = await response.json()
                    except (aiohttp.ContentTypeError, TypeError, ValueError) as err:
                        detail = _error_detail(err)
                        _LOGGER.debug(
                            "%s returned invalid JSON status=%s: %s",
                            action,
                            response.status,
                            detail,
                        )
                        return TokenEndpointResult(
                            reason="invalid_json",
                            status=response.status,
                            detail=detail,
                            body_preview=body_preview,
                        )
                    if not isinstance(parsed, dict):
                        detail = f"payload_type={type(parsed).__name__}"
                        _LOGGER.debug(
                            "%s returned unexpected payload type status=%s payload_type=%s",
                            action,
                            response.status,
                            type(parsed).__name__,
                        )
                        return TokenEndpointResult(
                            reason="invalid_payload",
                            status=response.status,
                            detail=detail,
                            body_preview=_response_preview(parsed),
                        )
                    if not parsed:
                        _LOGGER.debug(
                            "%s returned an empty payload status=%s",
                            action,
                            response.status,
                        )
                        return TokenEndpointResult(
                            reason="empty_response",
                            status=response.status,
                            body_preview=_response_preview(parsed),
                        )
                    try:
                        token = TokenResponse.from_dict(parsed)
                    except (KeyError, TypeError, ValueError) as err:
                        detail = _error_detail(err)
                        _LOGGER.debug(
                            "%s returned malformed payload status=%s: %s",
                            action,
                            response.status,
                            detail,
                        )
                        return TokenEndpointResult(
                            reason="invalid_payload",
                            status=response.status,
                            detail=detail,
                            body_preview=_response_preview(parsed),
                        )
                    _LOGGER.debug("%s successful", action)
                    return TokenEndpointResult(token=token, status=response.status)

                if response.status in (400, 401, 403):
                    _LOGGER.debug("%s rejected with status=%s", action, response.status)
                    return TokenEndpointResult(
                        reason=invalid_reason,
                        status=response.status,
                        body_preview=body_preview,
                    )

                _LOGGER.debug("%s failed with status=%s", action, response.status)
                return TokenEndpointResult(
                    reason="http_error",
                    status=response.status,
                    body_preview=body_preview,
                )
        except TimeoutError as err:
            detail = _error_detail(err)
            _LOGGER.debug("%s timeout: %s", action, detail)
            return TokenEndpointResult(reason="timeout", detail=detail)
        except aiohttp.ClientError as err:
            detail = _error_detail(err)
            _LOGGER.debug("%s network error: %s", action, detail)
            return TokenEndpointResult(reason="network_error", detail=detail)

    async def _response_text_preview(self, response: aiohttp.ClientResponse) -> str | None:
        """Read and shorten response text for diagnostics when available."""
        try:
            return _text_preview(await response.text())
        except (TypeError, ValueError, UnicodeDecodeError) as err:
            _LOGGER.debug("Could not read response text status=%s: %s", response.status, err)
            return None

    def _raise_token_endpoint_failure(
        self,
        result: TokenEndpointResult,
        *,
        invalid_reason: TokenFailureReason,
        invalid_message: str,
        connection_message: str,
        malformed_message: str,
        response_message: str,
    ) -> NoReturn:
        """Raise a typed SDK exception for a failed token endpoint result."""
        if result.reason == invalid_reason:
            raise HomelyAuthError(invalid_message)
        if result.reason in ("timeout", "network_error"):
            raise HomelyConnectionError(connection_message)
        if result.reason in ("invalid_json", "invalid_payload", "empty_response"):
            raise HomelyResponseError(
                malformed_message,
                status=result.status,
                body=result.body_preview,
                body_preview=result.body_preview,
            )
        raise HomelyResponseError(
            response_message,
            status=result.status,
            body=result.body_preview,
            body_preview=result.body_preview,
        )

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
                            "Locations fetch returned unexpected payload type "
                            "status=%s payload_type=%s",
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
                            "Location data fetch returned invalid JSON "
                            "status=%s location_id=%s: %s",
                            response.status,
                            _log_identifier(location_id),
                            err,
                        )
                        return None, response.status
                    if not isinstance(parsed, dict):
                        _LOGGER.debug(
                            "Location data fetch returned unexpected payload "
                            "type status=%s location_id=%s payload_type=%s",
                            response.status,
                            _log_identifier(location_id),
                            type(parsed).__name__,
                        )
                        return None, response.status
                    return parsed, response.status
                retry_after = response.headers.get("Retry-After")
                try:
                    body = await response.text()
                except Exception:
                    body = "<unreadable>"
                _LOGGER.debug(
                    "Location data fetch failed with status=%s location_id=%s "
                    "retry_after=%s body=%s",
                    response.status,
                    _log_identifier(location_id),
                    retry_after,
                    body[:500] if body else None,
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
