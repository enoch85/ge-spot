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
        self._cache = {}  # Cache to store API responses
        self._cache_ttl = config.get("cache_ttl", 60)  # Cache TTL in minutes
        
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
            
            # Generate cache key
            cache_key = f"{self.__class__.__name__}_{area}_{currency}_{date_str}"
            
            # Check if we have a valid cached response
            current_time = datetime.datetime.now()
            if cache_key in self._cache:
                cache_entry = self._cache[cache_key]
                cache_age = (current_time - cache_entry['timestamp']).total_seconds() / 60
                
                if cache_age < self._cache_ttl:
                    _LOGGER.debug(f"Using cached data for {cache_key} (age: {cache_age:.1f} min, TTL: {self._cache_ttl} min)")
                    return cache_entry['data']
                else:
                    _LOGGER.debug(f"Cached data expired for {cache_key} (age: {cache_age:.1f} min, TTL: {self._cache_ttl} min)")
            
            # Check rate limiting
            if self._should_skip_fetch(current_time):
                _LOGGER.debug(f"Skipping fetch for {area} on {date_str} due to rate limiting")
                if cache_key in self._cache:
                    _LOGGER.debug(f"Using older cached data despite expiry due to rate limiting")
                    return self._cache[cache_key]['data']
                elif self._last_successful_fetch:
                    return self._last_successful_fetch
                
            self._last_fetched = current_time
                
            # Fetch the raw data
            _LOGGER.debug(f"Fetching data for {area} on {date_str} with currency {currency}")
            raw_data = await self._fetch_data()
            
            _LOGGER.debug(f"API {self.__class__.__name__} raw response: {str(raw_data)[:1000]}...")
            
            if not raw_data:
                _LOGGER.error(f"No data received from API for {area} on {date_str}")
                return None
                
            # Process the data into a consistent format
            _LOGGER.debug(f"Processing raw data for {area}")
            processed_data = self._process_data(raw_data)
            
            if processed_data:
                # Store the raw, unmodified API response
                processed_data["raw_api_response"] = raw_data
                
                # Add source information
                processed_data["data_source"] = self.__class__.__name__
                
                # Add raw values to processed data
                if not "raw_values" in processed_data:
                    processed_data["raw_values"] = {}
                
                # Log conversions for debugging
                self._log_conversions(processed_data)
                
                # Mark as successful fetch
                self._last_successful_fetch = processed_data
                
                # Cache the result
                self._cache[cache_key] = {
                    'data': processed_data,
                    'timestamp': current_time
                }
                
                _LOGGER.debug(f"Successfully processed and cached data for {cache_key}")
            
            return processed_data
            
        except Exception as e:
            _LOGGER.error(f"Error fetching day-ahead prices: {str(e)}", exc_info=True)
            return None
    
    def _log_conversions(self, processed_data):
        """Log value conversions for debugging purposes."""
        _LOGGER.debug(f"Value conversions for {self.__class__.__name__}:")
        
        for key in ["current_price", "next_hour_price", "day_average_price", "peak_price", "off_peak_price"]:
            if key in processed_data and "raw_values" in processed_data and key in processed_data["raw_values"]:
                raw = processed_data["raw_values"][key]
                converted = processed_data[key]
                _LOGGER.debug(f"  - {key}: {raw} → {converted} (applied VAT {self.vat:.2%})")
    
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
            
        # Check if we have hourly prices in cache
        if self._last_successful_fetch and "hourly_prices" in self._last_successful_fetch:
            hourly_prices = self._last_successful_fetch["hourly_prices"]
            # If we already have prices for the current hour, limit API calls
            current_hour_str = f"{current_time.hour:02d}:00"
            if current_hour_str in hourly_prices:
                _LOGGER.debug(f"Rate limiting: Already have price for current hour {current_hour_str}")
                return time_diff < 60  # Only fetch once per hour if we have current price
        
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
        - raw_values: dict mapping keys to raw values before conversion
        """
        pass
    
    def _apply_vat(self, price):
        """Apply VAT to price."""
        if price is None:
            return None
        
        # Store the raw value before VAT application
        raw_value = price
        
        # Apply VAT
        result = price * (1 + self.vat)
        
        # Log the conversion for debugging
        _LOGGER.debug(f"Applied VAT {self.vat:.2%}: {raw_value} → {result}")
        
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
