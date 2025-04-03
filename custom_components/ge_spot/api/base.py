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
        self._last_fetched = None
        self._last_successful_fetch = None
        
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
            
            # Check rate limiting
            current_time = datetime.datetime.now()
            if self._should_skip_fetch(current_time):
                _LOGGER.debug(f"Skipping fetch for {area} on {date_str} due to rate limiting")
                if self._last_successful_fetch:
                    return self._last_successful_fetch
                
            self._last_fetched = current_time
                
            # Fetch the raw data
            _LOGGER.debug(f"Fetching data for {area} on {date_str} with currency {currency}")
            raw_data = await self._fetch_data()
            
            if not raw_data:
                _LOGGER.error(f"No data received from API for {area} on {date_str}")
                return None
                
            # Process the data into a consistent format
            _LOGGER.debug(f"Processing raw data: {str(raw_data)[:500]}...")
            processed_data = self._process_data(raw_data)
            
            if processed_data:
                # Store raw data in the processed result for transparency
                processed_data["raw_api_response"] = raw_data
                # Add source information
                processed_data["data_source"] = self.__class__.__name__
                # Mark as successful fetch
                self._last_successful_fetch = processed_data
            
            return processed_data
            
        except Exception as e:
            _LOGGER.error(f"Error fetching day-ahead prices: {str(e)}", exc_info=True)
            return None
    
    def _should_skip_fetch(self, current_time):
        """Determine if we should skip fetching based on rate limiting rules."""
        if not self._last_fetched:
            return False
            
        # Define different rate limiting rules based on data type
        time_diff = (current_time - self._last_fetched).total_seconds() / 60  # in minutes
        
        # If less than 15 minutes since last fetch, always skip
        if time_diff < 15:
            _LOGGER.debug(f"Rate limiting: Last fetch was only {time_diff:.1f} minutes ago")
            return True
            
        # Check time of day for special cases
        hour = current_time.hour
        
        # Between midnight and 1 AM - fetch today's new prices
        if 0 <= hour < 1:
            _LOGGER.debug("Rate limiting: First hour of day, allowing fetch for new daily prices")
            return False
            
        # Between 13:00-14:00 - fetch tomorrow's prices which typically become available
        if 13 <= hour < 14:
            _LOGGER.debug("Rate limiting: 13:00-14:00, allowing fetch for tomorrow's prices")
            return False
            
        # Standard rate limiting - don't fetch more than once per hour
        return time_diff < 60
    
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
        
        # Log the conversion for debugging
        result = price * (1 + self.vat)
        _LOGGER.debug(f"Applied VAT {self.vat:.2%}: {price} → {result}")
        return result
        
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
                    _LOGGER.debug(f"Response content type: {content_type}")
                    
                    response_text = await response.text()
                    _LOGGER.debug(f"Raw API response (first 1000 chars): {response_text[:1000]}")
                    
                    if 'application/json' in content_type:
                        try:
                            json_data = await response.json()
                            _LOGGER.debug(f"Parsed JSON data with {len(str(json_data))} characters")
                            return json_data
                        except Exception as e:
                            _LOGGER.error(f"Failed to parse response as JSON: {e}")
                            return response_text
                    else:
                        _LOGGER.warning(f"Unexpected content type: {content_type}")
                        # Try to parse as JSON anyway, but log warning
                        try:
                            import json
                            json_data = json.loads(response_text)
                            _LOGGER.debug("Successfully parsed response as JSON despite content type")
                            return json_data
                        except Exception as e:
                            _LOGGER.debug(f"Could not parse as JSON: {e}")
                            # Return the text in case caller wants to handle it
                            return response_text
                            
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
