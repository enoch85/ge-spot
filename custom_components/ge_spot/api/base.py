"""Base API implementation for energy prices."""
import logging
import datetime
import aiohttp
import asyncio
from abc import ABC, abstractmethod

from homeassistant.util import dt as dt_util
from homeassistant.core import HomeAssistant

from ..utils.currency_utils import async_convert_energy_price
from ..utils.timezone_utils import localize_datetime
from ..const import (
    REGION_TO_CURRENCY,
    CURRENCY_SUBUNIT_NAMES,
    ENERGY_UNIT_CONVERSION,
    CONF_API_KEY
)

_LOGGER = logging.getLogger(__name__)

class BaseEnergyAPI(ABC):
    """Base class for energy price APIs with robust error handling."""

    def __init__(self, config):
        """Initialize the API."""
        self.config = config
        self.session = None
        self.vat = config.get("vat", 0.0)
        self._currency = config.get("currency", "EUR")
        self._area = config.get("area")
        self._date_str = None
        self._last_fetched = None
        self._last_successful_fetch = None
        self._cache = {}  # Cache to store API responses
        self._cache_ttl = config.get("cache_ttl", 60)  # Cache TTL in minutes
        self.hass = None  # Will be set when used with Home Assistant

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

    async def validate_api_key(self, api_key=None):
        """Validate an API key.
        
        Args:
            api_key: Optional API key to validate (uses stored key if not provided)
            
        Returns:
            bool: True if the API key is valid, False otherwise
        """
        # Use provided key or get from config
        key_to_validate = api_key or self.config.get(CONF_API_KEY) or self.config.get("api_key")
        
        if not key_to_validate:
            _LOGGER.warning("No API key to validate")
            return False
            
        try:
            # Implementation depends on the specific API
            _LOGGER.debug(f"Validating API key (starting with {key_to_validate[:5]}...)")
            
            # Default implementation - will be overridden by subclasses
            # Simply try to fetch data with the key
            test_config = dict(self.config)
            test_config[CONF_API_KEY] = key_to_validate
            
            # Create a temporary instance with the test config
            temp_instance = self.__class__(test_config)
            if hasattr(self, "session") and self.session:
                temp_instance.session = self.session
                
            # Try to fetch data
            result = await temp_instance._fetch_data()
            
            # Close the temporary instance if needed
            if temp_instance != self and hasattr(temp_instance, "close"):
                await temp_instance.close()
                
            # Check if we got a valid response
            if result:
                _LOGGER.info("API key validation successful")
                return True
            else:
                _LOGGER.warning("API key validation failed: No data returned")
                return False
                
        except Exception as e:
            _LOGGER.error(f"API key validation error: {e}")
            return False

    async def fetch_day_ahead_prices(self, area, currency, date, hass=None):
        """Fetch day-ahead prices for a specific area and date."""
        try:
            # Store Home Assistant instance if provided
            if hass and isinstance(hass, HomeAssistant):
                self.hass = hass
                _LOGGER.debug(f"Home Assistant instance set for {self.__class__.__name__}")

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
            cached_data = await self._check_cache(cache_key)
            if cached_data:
                return cached_data

            # Check rate limiting
            current_time = datetime.datetime.now()
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

            if raw_data:
                _LOGGER.debug(f"API {self.__class__.__name__} raw response received")

            if not raw_data:
                _LOGGER.error(f"No data received from API for {area} on {date_str}")
                return None

            # Process the data into a consistent format
            _LOGGER.debug(f"Processing raw data for {area}")
            processed_data = await self._process_data(raw_data)

            if processed_data:
                # Log the raw API response but don't store it in processed data
                if "raw_api_response" in processed_data:
                    _LOGGER.debug(
                        "Raw API response for %s: %s bytes of data",
                        self.__class__.__name__,
                        len(str(processed_data["raw_api_response"]))
                    )
                    # Remove raw API response to prevent attribute size issues
                    processed_data.pop("raw_api_response", None)

                # Add source information
                processed_data["data_source"] = self.__class__.__name__

                # Add raw values to processed data
                if not "raw_values" in processed_data:
                    processed_data["raw_values"] = {}

                # Include Home Assistant timezone information
                if self.hass:
                    processed_data["ha_timezone"] = str(self.hass.config.time_zone)

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

    async def _check_cache(self, cache_key):
        """Check if we have a valid cached response."""
        current_time = datetime.datetime.now()

        if cache_key in self._cache:
            cache_entry = self._cache[cache_key]
            cache_age = (current_time - cache_entry['timestamp']).total_seconds() / 60

            if cache_age < self._cache_ttl:
                _LOGGER.debug(f"Using cached data for {cache_key} (age: {cache_age:.1f} min, TTL: {self._cache_ttl} min)")
                return cache_entry['data']
            else:
                _LOGGER.debug(f"Cached data expired for {cache_key} (age: {cache_age:.1f} min, TTL: {self._cache_ttl} min)")

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
    async def _process_data(self, raw_data):
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

    async def _convert_price(self, price, from_currency="EUR", from_unit="MWh", to_subunit=None, exchange_rate=None):
        """Convert price using centralized conversion logic."""
        if price is None:
            return None

        use_subunit = to_subunit if to_subunit is not None else self.config.get("price_in_cents", False)
        
        from ..utils.debug_utils import log_conversion
        from ..utils.currency_utils import async_convert_energy_price

        # Store original for logging
        original_price = price
        
        # Get exchange rate if available (for logging)
        session = getattr(self, "session", None)

        # Perform conversion
        converted_price = await async_convert_energy_price(
            price=price,
            from_unit=from_unit,
            to_unit="kWh",
            from_currency=from_currency,
            to_currency=self._currency,
            vat=self.vat,
            to_subunit=use_subunit,
            session=session,
            exchange_rate=exchange_rate
        )
        
        # Log details
        log_conversion(
            original=original_price,
            converted=converted_price,
            from_currency=from_currency,
            to_currency=self._currency,
            from_unit=from_unit,
            to_unit="kWh",
            vat=self.vat
        )
            
        return converted_price

    def _get_now(self):
        """Get current datetime in Home Assistant's timezone if available."""
        if hasattr(self, 'hass') and self.hass:
            now_utc = dt_util.utcnow()
            return localize_datetime(now_utc, self.hass)
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

    def _apply_vat(self, price, vat_rate=None):
        """Apply VAT to a price value."""
        if price is None:
            return None
            
        # Use provided VAT rate or fall back to instance VAT
        vat = vat_rate if vat_rate is not None else self.vat
        
        if vat > 0:
            original_price = price
            price = price * (1 + vat)
            _LOGGER.debug(f"Applied VAT {vat:.2%}: {original_price} → {price}")
        else:
            _LOGGER.debug(f"No VAT applied (rate: {vat:.2%})")
            
        return price
