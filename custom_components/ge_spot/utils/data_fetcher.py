"""Data fetching utilities for API requests."""
import logging
import asyncio
import aiohttp
from typing import Dict, Any, Optional

from ..const.network import Network

_LOGGER = logging.getLogger(__name__)

class DataFetcher:
    """Unified data fetcher with retry logic and error handling."""

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        """Initialize with optional session."""
        self.session = session
        self._owns_session = session is None

    async def ensure_session(self):
        """Ensure that a valid session exists."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
            self._owns_session = True

    async def fetch_with_retry(self, url: str,
                             params: Optional[Dict] = None,
                             headers: Optional[Dict] = None,
                             timeout: int = Network.Defaults.PARALLEL_FETCH_TIMEOUT,
                             max_retries: int = Network.Defaults.RETRY_COUNT) -> Any:
        """Fetch data with retry logic."""
        await self.ensure_session()

        for attempt in range(max_retries):
            try:
                _LOGGER.debug(f"Request attempt {attempt+1}/{max_retries}: {url}")

                async with self.session.get(url,
                                            params=params,
                                            headers=headers,
                                            timeout=timeout) as response:
                    if response.status != 200:
                        _LOGGER.error(f"HTTP error {response.status} fetching from {url} (attempt {attempt+1}/{max_retries})")

                        # Try to get error details
                        if response.status != 404:
                            try:
                                error_text = await response.text()
                                _LOGGER.debug(f"Error response: {error_text[:500]}...")
                            except:
                                pass

                        if attempt < max_retries - 1:
                            await self._backoff(attempt)
                            continue
                        return None

                    # Handle response based on content type
                    content_type = response.headers.get('Content-Type', '').lower()

                    if 'application/json' in content_type:
                        return await response.json()
                    else:
                        return await response.text()

            except asyncio.TimeoutError:
                _LOGGER.error(f"Timeout fetching from {url} (attempt {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    await self._backoff(attempt)
                    continue
                return None

            except Exception as e:
                _LOGGER.error(f"Error fetching from {url}: {e}")
                if attempt < max_retries - 1:
                    await self._backoff(attempt)
                    continue
                return None

        return None

    async def _backoff(self, attempt: int):
        """Perform exponential backoff."""
        delay = Network.Defaults.RETRY_BASE_DELAY * (2 ** attempt)
        _LOGGER.debug(f"Retrying in {delay:.1f} seconds...")
        await asyncio.sleep(delay)

    async def close(self):
        """Close the session if we own it."""
        if self._owns_session and self.session and not self.session.closed:
            await self.session.close()
            self.session = None
