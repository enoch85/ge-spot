"""API client utilities for GE-Spot integration."""
import logging
import asyncio
from typing import Dict, Any, Optional, List, Callable, Awaitable
import aiohttp

from ..const.attributes import Attributes

_LOGGER = logging.getLogger(__name__)

class ApiClient:
    """Generic API client with improved error handling."""

    def __init__(self, session: Optional[aiohttp.ClientSession] = None, pool_size: int = 10):
        """Initialize the API client.

        Args:
            session: Optional aiohttp ClientSession to use
            pool_size: Size of the connection pool
        """
        self.session = session
        self.pool_size = pool_size
        self._semaphore = asyncio.Semaphore(pool_size)
        self._timeout = aiohttp.ClientTimeout(total=30)
        self._headers = {
            "User-Agent": "GE-Spot/1.0",
            "Accept": "application/json"
        }

    async def get(self, url: str, params: Optional[Dict[str, Any]] = None,
                 headers: Optional[Dict[str, str]] = None, timeout: Optional[int] = None,
                 encoding: Optional[str] = None) -> Any:
        """Perform a GET request with error handling.

        Args:
            url: The URL to request
            params: Optional query parameters
            headers: Optional request headers
            timeout: Optional timeout in seconds
            encoding: Optional encoding for text responses (e.g., 'utf-8', 'iso-8859-1')

        Returns:
            The response data as a dictionary or string depending on content type
        """
        merged_headers = {**self._headers, **(headers or {})}
        timeout_obj = aiohttp.ClientTimeout(total=timeout) if timeout else self._timeout

        async with self._semaphore:
            try:
                if self.session:
                    async with self.session.get(url, params=params, headers=merged_headers,
                                              timeout=timeout_obj) as response:
                        if response.status != 200:
                            _LOGGER.error(f"API request failed with status {response.status}: {url}")
                            return {}

                        # Check content type to determine how to parse the response
                        content_type = response.headers.get('Content-Type', '').lower()

                        if 'application/json' in content_type:
                            return await response.json()
                        elif 'text/xml' in content_type or 'application/xml' in content_type:
                            return await response.text(encoding=encoding)
                        else:
                            # Try JSON first, fall back to text if that fails
                            try:
                                return await response.json()
                            except:
                                return await response.text(encoding=encoding)
                else:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, params=params, headers=merged_headers,
                                             timeout=timeout_obj) as response:
                            if response.status != 200:
                                _LOGGER.error(f"API request failed with status {response.status}: {url}")
                                return {}

                            # Check content type to determine how to parse the response
                            content_type = response.headers.get('Content-Type', '').lower()

                            if 'application/json' in content_type:
                                return await response.json()
                            elif 'text/xml' in content_type or 'application/xml' in content_type:
                                return await response.text(encoding=encoding)
                            else:
                                # Try JSON first, fall back to text if that fails
                                try:
                                    return await response.json()
                                except:
                                    return await response.text(encoding=encoding)
            except asyncio.TimeoutError:
                _LOGGER.error(f"API request timed out: {url}")
                return {}
            except aiohttp.ClientError as e:
                _LOGGER.error(f"API request failed: {url} - {e}")
                return {}
            except Exception as e:
                _LOGGER.error(f"Unexpected error in API request: {url} - {e}")
                return {}

    async def fetch(self, url: str, params: Optional[Dict[str, Any]] = None,
                  headers: Optional[Dict[str, str]] = None, timeout: Optional[int] = None,
                  encoding: Optional[str] = None, response_format: Optional[str] = None) -> Any:
        """Fetch data with improved error handling.

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
        merged_headers = {**self._headers, **(headers or {})}
        timeout_obj = aiohttp.ClientTimeout(total=timeout) if timeout else self._timeout

        # Adjust Accept header based on response_format
        if response_format:
            if response_format.lower() == 'json':
                merged_headers['Accept'] = 'application/json'
            elif response_format.lower() == 'xml':
                merged_headers['Accept'] = 'application/xml, text/xml'
            elif response_format.lower() == 'text' or response_format.lower() == 'csv':
                merged_headers['Accept'] = 'text/plain, text/csv, */*'

        async with self._semaphore:
            try:
                if self.session:
                    async with self.session.get(url, params=params, headers=merged_headers,
                                              timeout=timeout_obj) as response:
                        # Check for HTTP errors
                        if response.status != 200:
                            _LOGGER.error(f"API request failed with status {response.status}: {url}")

                            # Try to get more detailed error information
                            try:
                                error_text = await response.text(encoding=encoding)
                                # Return error information instead of empty dict
                                return {
                                    "error": True,
                                    "status_code": response.status,
                                    "message": error_text[:500] if len(error_text) > 500 else error_text,
                                    "url": url
                                }
                            except Exception as e:
                                _LOGGER.debug(f"Could not extract error text: {e}")
                                # Fallback error info
                                return {
                                    "error": True,
                                    "status_code": response.status,
                                    "message": f"HTTP {response.status}",
                                    "url": url
                                }

                        # Process successful response based on format parameter or content type
                        if response_format:
                            if response_format.lower() in ['text', 'csv']:
                                return await response.text(encoding=encoding)
                            elif response_format.lower() == 'json':
                                return await response.json()
                            elif response_format.lower() == 'xml':
                                return await response.text(encoding=encoding)
                        
                        # If no specific format requested, check content type
                        content_type = response.headers.get('Content-Type', '').lower()

                        if 'application/json' in content_type:
                            return await response.json()
                        elif 'text/xml' in content_type or 'application/xml' in content_type:
                            return await response.text(encoding=encoding)
                        elif 'text/csv' in content_type or 'text/plain' in content_type:
                            return await response.text(encoding=encoding)
                        else:
                            # Try JSON first, fall back to text if that fails
                            try:
                                return await response.json()
                            except:
                                return await response.text(encoding=encoding)
                else:
                    # Create temporary session if none exists
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, params=params, headers=merged_headers,
                                             timeout=timeout_obj) as response:
                            if response.status != 200:
                                _LOGGER.error(f"API request failed with status {response.status}: {url}")

                                try:
                                    error_text = await response.text(encoding=encoding)
                                    return {
                                        "error": True,
                                        "status_code": response.status,
                                        "message": error_text[:500] if len(error_text) > 500 else error_text,
                                        "url": url
                                    }
                                except Exception as e:
                                    _LOGGER.debug(f"Could not extract error text: {e}")
                                    return {
                                        "error": True,
                                        "status_code": response.status,
                                        "message": f"HTTP {response.status}",
                                        "url": url
                                    }

                            # Process successful response based on format parameter or content type
                            if response_format:
                                if response_format.lower() in ['text', 'csv']:
                                    return await response.text(encoding=encoding)
                                elif response_format.lower() == 'json':
                                    return await response.json()
                                elif response_format.lower() == 'xml':
                                    return await response.text(encoding=encoding)
                            
                            # If no specific format requested, check content type
                            content_type = response.headers.get('Content-Type', '').lower()

                            if 'application/json' in content_type:
                                return await response.json()
                            elif 'text/xml' in content_type or 'application/xml' in content_type:
                                return await response.text(encoding=encoding)
                            elif 'text/csv' in content_type or 'text/plain' in content_type:
                                return await response.text(encoding=encoding)
                            else:
                                try:
                                    return await response.json()
                                except:
                                    return await response.text(encoding=encoding)
            except asyncio.TimeoutError:
                _LOGGER.error(f"API request timed out: {url}")
                return {"error": True, "message": "Request timed out", "url": url}
            except aiohttp.ClientError as e:
                _LOGGER.error(f"API request failed: {url} - {e}")
                return {"error": True, "message": str(e), "url": url}
            except Exception as e:
                _LOGGER.error(f"Unexpected error in API request: {url} - {e}")
                return {"error": True, "message": f"Unexpected error: {str(e)}", "url": url}

    async def close(self) -> None:
        """Close the session if it was created by this instance."""
        if self.session and not hasattr(self.session, '_is_external'):
            await self.session.close()

class ApiFallbackManager:
    """Manage API fallbacks with priority-based retries."""

    def __init__(self, apis: List[Any]):
        """Initialize the fallback manager.

        Args:
            apis: List of API instances in priority order
        """
        self.apis = apis
        self.primary_api = apis[0] if apis else None
        self.active_api = None
        self.fallback_used = False
        self.attempted_sources = []

    async def fetch_with_fallback(self, fetch_method: str, *args, **kwargs) -> Any:
        """Fetch data using fallback chain if needed.

        Args:
            fetch_method: The name of the method to call on each API
            *args: Arguments to pass to the fetch method
            **kwargs: Keyword arguments to pass to the fetch method

        Returns:
            The fetched data or None if all sources fail
        """
        result = None
        self.attempted_sources = []
        self.fallback_used = False

        for api in self.apis:
            api_name = api.__class__.__name__
            self.attempted_sources.append(api_name)

            try:
                # Get the method by name
                method = getattr(api, fetch_method)
                if not method or not callable(method):
                    _LOGGER.error(f"Method {fetch_method} not found on {api_name}")
                    continue

                _LOGGER.debug(f"Attempting to fetch data from {api_name}")
                result = await method(*args, **kwargs)

                if result:
                    self.active_api = api
                    self.fallback_used = api != self.primary_api
                    _LOGGER.debug(f"Successfully retrieved data from {api_name}")

                    # Add metadata about source if result is a dictionary
                    if isinstance(result, dict):
                        result[Attributes.DATA_SOURCE] = api_name
                        result[Attributes.FALLBACK_USED] = self.fallback_used
                    # For string results (like XML), we can't add metadata
                    # but we still return the result

                    return result
                else:
                    _LOGGER.warning(f"No data retrieved from {api_name}")

            except Exception as e:
                _LOGGER.error(f"Error fetching data from {api_name}: {e}")

        _LOGGER.error(f"Failed to fetch data from any source. Attempted: {', '.join(self.attempted_sources)}")
        return None
