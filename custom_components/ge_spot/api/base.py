"""Base API implementation for energy prices."""
import logging
import datetime
import aiohttp
import asyncio
from abc import ABC, abstractmethod

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

class BaseEnergyAPI(ABC):
    """Base class for energy price APIs with robust error handling."""
    
    def __init__(self, config):
        """Initialize the API."""
        self.config = config
        self.session = None
        self.vat = config.get("vat", 0.0)
        self._currency = config.get("currency", "EUR")
        self._area = None
        self._date_str = None
        
    async def _ensure_session(self):
        """Ensure that we have an aiohttp session."""
        try:
            if self.session is None:
                _LOGGER.debug(f"Creating new aiohttp session for {self.__class__.__name__}")
                self.session = aiohttp.ClientSession()
        except Exception as e:
            _LOGGER.error(f"Error creating session in {self.__class__.__name__}: {str(e)}")
            
    async def close(self):
        """Close the session."""
        if self.session:
            try:
                await self.session.close()
            except Exception as e:
                _LOGGER.error(f"Error closing session: {str(e)}")
            finally:
                self.session = None
    
    async def fetch_day_ahead_prices(self, area, currency, date):
        """Fetch day-ahead prices for a specific area and date."""
        try:
            # Ensure we have a session
            await self._ensure_session()
            
            if not self.session:
                _LOGGER.error(f"Could not create session for {self.__class__.__name__}")
                return None
            
            # Format the date consistently
            if isinstance(date, datetime.datetime):
                date_str = date.strftime("%Y-%m-%d")
            else:
                date_str = date
                
            # Store current configuration
            self._area = area
            self._currency = currency
            self._date_str = date_str
            
            # Fetch the raw data
            raw_data = await self._fetch_data()
            
            if not raw_data:
                return None
                
            # Process the data into a consistent format
            processed_data = self._process_data(raw_data)
            
            return processed_data
            
        except Exception as e:
            _LOGGER.error(f"Error fetching day-ahead prices: {str(e)}", exc_info=True)
            return None
    
    @abstractmethod
    async def _fetch_data(self):
        """Fetch raw price data from the API. To be implemented by subclasses."""
        pass
        
    @abstractmethod
    def _process_data(self, raw_data):
        """Process raw price data into a consistent format.
        
        The expected output format is a dictionary with keys like:
        - current_price: price for current hour
        - next_hour_price: price for next hour
        - day_average_price: average price for the day
        - peak_price: highest price of the day
        - off_peak_price: lowest price of the day
        - hourly_prices: dict mapping hour strings to prices
        """
        pass
    
    def _apply_vat(self, price):
        """Apply VAT to price."""
        if price is None:
            return None
        return price * (1 + self.vat)
        
    def _get_now(self):
        """Get current datetime. Separate method for easier testing."""
        return datetime.datetime.now()
        
    async def _fetch_with_retry(self, url, params=None, max_retries=3):
        """Fetch data from URL with retry mechanism."""
        await self._ensure_session()
        
        if not self.session:
            _LOGGER.error("No session available for API request")
            return None
            
        for attempt in range(max_retries):
            try:
                _LOGGER.debug(f"API request attempt {attempt+1}/{max_retries}: {url} with params {params}")
                async with self.session.get(url, params=params, timeout=30) as response:
                    if response.status != 200:
                        _LOGGER.error(f"Error fetching from URL (attempt {attempt+1}/{max_retries}): HTTP {response.status}")
                        
                        # Log response body for debugging if not successful
                        if response.status != 404:  # Don't log 404 body as it's usually large error pages
                            try:
                                error_text = await response.text()
                                _LOGGER.debug(f"Error response (first 500 chars): {error_text[:500]}")
                            except:
                                _LOGGER.debug("Could not read error response body")
                                
                        if attempt < max_retries - 1:
                            retry_delay = 2 ** attempt  # Exponential backoff
                            _LOGGER.debug(f"Retrying in {retry_delay} seconds...")
                            await asyncio.sleep(retry_delay)
                            continue
                        return None
                    
                    # Check content type to handle response appropriately
                    content_type = response.headers.get('Content-Type', '')
                    
                    if 'application/json' in content_type:
                        return await response.json()
                    else:
                        _LOGGER.warning(f"Unexpected content type: {content_type}")
                        # Try to parse as JSON anyway, but log warning
                        try:
                            return await response.json()
                        except Exception as e:
                            _LOGGER.error(f"Failed to parse response as JSON: {e}")
                            # Return the text in case caller wants to handle it
                            return await response.text()
                            
            except asyncio.TimeoutError:
                _LOGGER.error(f"Timeout fetching from URL (attempt {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    retry_delay = 2 ** attempt  # Exponential backoff
                    await asyncio.sleep(retry_delay)
                    continue
                raise
            except Exception as e:
                _LOGGER.error(f"Error in _fetch_with_retry: {str(e)}", exc_info=True)
                if attempt < max_retries - 1:
                    retry_delay = 2 ** attempt  # Exponential backoff
                    await asyncio.sleep(retry_delay)
                    continue
                raise
        
        return None
