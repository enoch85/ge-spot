"""API client utilities for GE-Spot integration."""
import logging
import asyncio
from typing import Dict, Any, Optional, List, Callable, Awaitable
import aiohttp

from ..const import ATTR_DATA_SOURCE, ATTR_FALLBACK_USED

_LOGGER = logging.getLogger(__name__)

class ApiClient:
    """Generic API client with improved error handling."""
    
    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        """Initialize the API client."""
        self.session = session
        self._retry_count = 3
        self._base_delay = 2.0
    
    async def ensure_session(self):
        """Ensure that we have a valid aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
    
    async def fetch(self, url: str, params: Optional[Dict] = None, timeout: int = 30) -> Any:
        """Fetch data with improved error handling and logging.
        
        Args:
            url: The URL to fetch
            params: Optional query parameters
            timeout: Request timeout in seconds
            
        Returns:
            The response data (JSON or text) or None on failure
        """
        await self.ensure_session()
        
        for attempt in range(self._retry_count):
            try:
                _LOGGER.debug(f"API request attempt {attempt+1}/{self._retry_count}: {url}")
                async with self.session.get(url, params=params, timeout=timeout) as response:
                    if response.status != 200:
                        _LOGGER.error(f"HTTP error {response.status} fetching from {url} (attempt {attempt+1}/{self._retry_count})")
                        
                        # Try to get error details for better diagnostics
                        if response.status != 404:
                            try:
                                error_text = await response.text()
                                _LOGGER.debug(f"Error response: {error_text[:500]}...")
                            except:
                                pass
                                
                        if attempt < self._retry_count - 1:
                            await self._do_backoff(attempt)
                            continue
                        return None
                    
                    # Get the content type to handle response appropriately
                    content_type = response.headers.get('Content-Type', '').lower()
                    
                    if 'application/json' in content_type:
                        return await response.json()
                    else:
                        return await response.text()
                        
            except asyncio.TimeoutError:
                _LOGGER.error(f"Timeout fetching from {url} (attempt {attempt+1}/{self._retry_count})")
                if attempt < self._retry_count - 1:
                    await self._do_backoff(attempt)
                    continue
                return None
                
            except Exception as e:
                _LOGGER.error(f"Error fetching from {url}: {e}")
                if attempt < self._retry_count - 1:
                    await self._do_backoff(attempt)
                    continue
                return None
                
        return None
    
    async def _do_backoff(self, attempt: int):
        """Perform exponential backoff.
        
        Args:
            attempt: The current attempt number (0-based)
        """
        delay = self._base_delay * (2 ** attempt)
        _LOGGER.debug(f"Retrying in {delay:.1f} seconds...")
        await asyncio.sleep(delay)
    
    async def close(self):
        """Close the session."""
        if self.session and not self.session.closed:
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
    
    async def fetch_with_fallback(self, fetch_method: str, *args, **kwargs) -> Dict[str, Any]:
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
                    
                    # Add metadata about source
                    if isinstance(result, dict):
                        result[ATTR_DATA_SOURCE] = api_name
                        result[ATTR_FALLBACK_USED] = self.fallback_used
                    
                    return result
                else:
                    _LOGGER.warning(f"No data retrieved from {api_name}")
            
            except Exception as e:
                _LOGGER.error(f"Error fetching data from {api_name}: {e}")
        
        _LOGGER.error(f"Failed to fetch data from any source. Attempted: {', '.join(self.attempted_sources)}")
        return None
