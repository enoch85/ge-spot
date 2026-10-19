"""API client utilities for GE-Spot integration."""

import json
import logging
import asyncio
from typing import Any, Dict, Optional
import aiohttp

from ...const.network import Network

_LOGGER = logging.getLogger(__name__)


class ApiClient:
    """Generic API client with improved error handling."""

    def __init__(self, session: aiohttp.ClientSession, pool_size: int = 10):
        """Initialize the API client.

        Args:
            session: aiohttp ClientSession to use. Required -- callers inject
                Home Assistant's shared session via async_get_clientsession(hass)
                rather than letting the client open its own. Opening a session
                here would block the event loop loading SSL certs and is
                discouraged by HA's inject-websession quality rule.
            pool_size: Size of the connection pool
        """
        if session is None:
            raise ValueError(
                "ApiClient requires an aiohttp session; inject "
                "async_get_clientsession(hass) instead of creating one."
            )
        self.session = session
        self.pool_size = pool_size
        self._semaphore = asyncio.Semaphore(pool_size)
        self._timeout = aiohttp.ClientTimeout(total=Network.Defaults.HTTP_TIMEOUT)
        self._headers = {"User-Agent": "GE-Spot/1.0", "Accept": "application/json"}
        self._consecutive_error_counts = {}
        self._rate_limit_detected = {}
        self._server_error_detected = {}

    async def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        encoding: Optional[str] = None,
    ) -> Any:
        """Perform a GET request with error handling.

        Args:
            url: The URL to request
            params: Optional query parameters
            headers: Optional request headers
            timeout: Optional timeout in seconds
            encoding: Optional encoding for text responses (e.g. 'utf-8', 'iso-8859-1')

        Returns:
            The response data as a dictionary or string depending on content type
        """
        merged_headers = {**self._headers, **(headers or {})}
        timeout_obj = aiohttp.ClientTimeout(total=timeout) if timeout else self._timeout

        async with self._semaphore:
            try:
                async with self.session.get(
                    url, params=params, headers=merged_headers, timeout=timeout_obj
                ) as response:
                    # HTTP 204 = No Content - data not published yet (not an error)
                    if response.status == 204:
                        _LOGGER.debug(
                            f"API returned 204 (No Content) - data not yet published: {url}"
                        )
                        return {"status": 204, "message": "Data not yet published"}

                    if response.status != 200:
                        _LOGGER.log(
                            (
                                logging.DEBUG
                                if response.status in (404, 429, 500, 502, 503, 504)
                                else logging.ERROR
                            ),
                            "API request failed with status %s: %s",
                            response.status,
                            url,
                        )
                        return {}

                    # Check content type to determine how to parse the response
                    content_type = response.headers.get("Content-Type", "").lower()

                    if "application/json" in content_type:
                        return await response.json()
                    elif (
                        "text/xml" in content_type or "application/xml" in content_type
                    ):
                        return await response.text(encoding=encoding)
                    else:
                        # Try JSON first, fall back to text if that fails.
                        # Narrow the catch so KeyboardInterrupt/SystemExit propagate:
                        #   ContentTypeError = Content-Type didn't match application/json
                        #   JSONDecodeError  = body wasn't valid JSON
                        try:
                            return await response.json()
                        except (aiohttp.ContentTypeError, json.JSONDecodeError):
                            return await response.text(encoding=encoding)
            except asyncio.TimeoutError:
                _LOGGER.debug(f"API request timed out: {url}")
                return {}
            except aiohttp.ClientError as e:
                _LOGGER.debug(f"API request failed: {url} - {e}")
                return {}
            except Exception as e:
                _LOGGER.error(f"Unexpected error in API request: {url} - {e}")
                return {}

    async def fetch(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        encoding: Optional[str] = None,
        response_format: Optional[str] = None,
    ) -> Any:
        """Fetch data with improved error handling.

        A server error or dropped connection is retried once after a short
        pause. API adapters report every failed request as missing data, so a
        retry here is the only one a transient failure gets.

        Args:
            url: The URL to request
            params: Optional query parameters
            headers: Optional request headers
            timeout: Optional timeout in seconds
            encoding: Optional encoding for text responses
            response_format: Optional format to force ('json', 'text', 'xml')

        Returns:
            The response data as a dictionary, string, or error information
        """
        for attempt in range(Network.Defaults.TRANSIENT_RETRY_COUNT + 1):
            result = await self._fetch_once(
                url, params, headers, timeout, encoding, response_format
            )
            if (
                not isinstance(result, dict)
                or not result.get("transient")
                or attempt == Network.Defaults.TRANSIENT_RETRY_COUNT
            ):
                return result
            _LOGGER.debug(
                f"Transient failure ({result.get('message', '')[:100]}), "
                f"retrying: {url}"
            )
            await asyncio.sleep(Network.Defaults.TRANSIENT_RETRY_DELAY_SECONDS)

    async def _fetch_once(
        self,
        url: str,
        params: Optional[Dict[str, Any]],
        headers: Optional[Dict[str, str]],
        timeout: Optional[int],
        encoding: Optional[str],
        response_format: Optional[str],
    ) -> Any:
        """Make one request; error results mark server/connection failures transient."""
        merged_headers = {**self._headers, **(headers or {})}
        timeout_obj = aiohttp.ClientTimeout(total=timeout) if timeout else self._timeout

        # Adjust Accept header based on response_format
        if response_format:
            if response_format.lower() == "json":
                merged_headers["Accept"] = "application/json"
            elif response_format.lower() == "xml":
                merged_headers["Accept"] = "application/xml, text/xml"
            elif response_format.lower() == "text" or response_format.lower() == "csv":
                merged_headers["Accept"] = "text/plain, text/csv, */*"

        async with self._semaphore:
            try:
                async with self.session.get(
                    url, params=params, headers=merged_headers, timeout=timeout_obj
                ) as response:
                    # Check for HTTP errors
                    if response.status != 200:
                        # Track consecutive errors for rate limit detection
                        self._track_error_response(url, response.status)

                        if response.status == 429:
                            # The coordinator reports sustained loss of usable prices.
                            _LOGGER.debug(
                                f"Rate limited (HTTP 429), will fall back / "
                                f"retry later: {url}"
                            )
                        elif response.status in (204, 404, 500, 502, 503, 504):
                            _LOGGER.debug(
                                f"Upstream temporarily unavailable "
                                f"(HTTP {response.status}), will retry / "
                                f"fall back: {url}"
                            )
                        else:
                            _LOGGER.error(
                                f"API request failed with status {response.status}: {url}"
                            )

                        transient = (
                            response.status in Network.Defaults.TRANSIENT_HTTP_STATUSES
                        )
                        # Try to get more detailed error information
                        try:
                            error_text = await response.text(encoding=encoding)
                            # Return error information instead of empty dict
                            return {
                                "error": True,
                                "status_code": response.status,
                                "message": (
                                    error_text[:500]
                                    if len(error_text) > 500
                                    else error_text
                                ),
                                "url": url,
                                "transient": transient,
                            }
                        except Exception as e:
                            _LOGGER.debug(f"Could not extract error text: {e}")
                            # Fallback error info
                            return {
                                "error": True,
                                "status_code": response.status,
                                "message": f"HTTP {response.status}",
                                "url": url,
                                "transient": transient,
                            }

                    # Success - reset error tracking
                    self._reset_error_tracking(url)

                    # Process successful response based on format parameter or content type
                    if response_format:
                        if response_format.lower() in ["text", "csv"]:
                            return await response.text(encoding=encoding)
                        elif response_format.lower() == "json":
                            return await response.json()
                        elif response_format.lower() == "xml":
                            return await response.text(encoding=encoding)

                    # If no specific format requested, check content type
                    content_type = response.headers.get("Content-Type", "").lower()

                    if "application/json" in content_type:
                        return await response.json()
                    elif (
                        "text/xml" in content_type or "application/xml" in content_type
                    ):
                        return await response.text(encoding=encoding)
                    elif "text/csv" in content_type or "text/plain" in content_type:
                        return await response.text(encoding=encoding)
                    else:
                        # Try JSON first, fall back to text if that fails.
                        # Narrow the catch so KeyboardInterrupt/SystemExit propagate:
                        #   ContentTypeError = Content-Type didn't match application/json
                        #   JSONDecodeError  = body wasn't valid JSON
                        try:
                            return await response.json()
                        except (aiohttp.ContentTypeError, json.JSONDecodeError):
                            return await response.text(encoding=encoding)
            except asyncio.TimeoutError:
                _LOGGER.debug(f"API request timed out: {url}")
                return {"error": True, "message": "Request timed out", "url": url}
            except aiohttp.ClientError as e:
                _LOGGER.debug(f"API request failed: {url} - {e}")
                return {"error": True, "message": str(e), "url": url, "transient": True}
            except Exception as e:
                _LOGGER.error(f"Unexpected error in API request: {url} - {e}")
                return {
                    "error": True,
                    "message": f"Unexpected error: {str(e)}",
                    "url": url,
                }

    def _track_error_response(self, url: str, status_code: int) -> None:
        """Track consecutive error responses for rate limit detection.

        Args:
            url: The URL that failed
            status_code: HTTP status code
        """
        url_key = url.split("?")[0]  # Use base URL without params

        if status_code == 429:
            # Explicit rate limiting
            if url_key not in self._rate_limit_detected:
                _LOGGER.debug(
                    f"Rate limit detected (HTTP 429) for {url_key}. "
                    f"Integration will automatically retry later."
                )
            self._rate_limit_detected[url_key] = True
        elif status_code in (502, 503, 504):
            # Reset transient upstream failure tracking on the next success.
            if url_key not in self._server_error_detected:
                _LOGGER.debug(
                    f"Upstream temporarily unavailable (HTTP {status_code}) for "
                    f"{url_key}. Transient; integration will retry / fall back."
                )
            self._server_error_detected[url_key] = True
        elif status_code == 404:
            # Track missing resources without guessing their cause.
            self._consecutive_error_counts[url_key] = (
                self._consecutive_error_counts.get(url_key, 0) + 1
            )
            if self._consecutive_error_counts[url_key] >= 3:
                if url_key not in self._rate_limit_detected:
                    _LOGGER.debug(
                        f"Repeated 404 errors for {url_key} "
                        f"({self._consecutive_error_counts[url_key]} consecutive). "
                        f"Integration will retry later."
                    )
                self._rate_limit_detected[url_key] = True

    def _reset_error_tracking(self, url: str) -> None:
        """Reset error tracking for a URL after successful request.

        Args:
            url: The URL that succeeded
        """
        url_key = url.split("?")[0]
        if url_key in self._consecutive_error_counts:
            del self._consecutive_error_counts[url_key]
        if url_key in self._rate_limit_detected:
            del self._rate_limit_detected[url_key]
        if url_key in self._server_error_detected:
            del self._server_error_detected[url_key]

    async def close(self) -> None:
        """No-op: the aiohttp session is injected and owned by the caller.

        The session comes from Home Assistant's async_get_clientsession and is
        shared across the integration (and others), so this client must never
        close it. Kept so existing call sites remain valid.
        """
        return
