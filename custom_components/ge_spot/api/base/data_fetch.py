"""Data fetching and processing for energy APIs."""
import logging
import datetime
from typing import Optional

from homeassistant.core import HomeAssistant

from .session_manager import ensure_session, fetch_with_retry
from ...const import CONF_API_KEY
from ...utils.timezone_utils import localize_datetime

_LOGGER = logging.getLogger(__name__)

class DataFetcher:
    """Handles data fetching and caching for API implementations."""

    def __init__(self, api_instance):
        """Initialize the data fetcher.
        
        Args:
            api_instance: The API instance that owns this fetcher
        """
        self.api = api_instance
        self.config = api_instance.config
        self._area = api_instance._area
        self._currency = api_instance._currency
        self._date_str = api_instance._date_str
        self._last_fetched = api_instance._last_fetched
        self._last_successful_fetch = api_instance._last_successful_fetch
        self._cache = api_instance._cache
        self._cache_ttl = api_instance._cache_ttl
        self.session = api_instance.session
        self._owns_session = api_instance._owns_session

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
            temp_instance = self.api.__class__(test_config)
            temp_owns_session = False

            # Use existing session if available to avoid creating too many
            if hasattr(self.api, "session") and self.api.session and not self.api.session.closed:
                temp_instance.session = self.api.session
            else:
                # Create a session for validation if needed
                await ensure_session(temp_instance)
                temp_owns_session = True

            # Try to fetch data
            result = await temp_instance._fetch_data()

            # Close the temporary instance session if we created it
            if temp_owns_session and hasattr(temp_instance, 'close'):
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
                self.api.hass = hass
                _LOGGER.debug(f"Home Assistant instance set for {self.api.__class__.__name__}")

            # Ensure we have a session
            await ensure_session(self.api)

            if not self.api.session or self.api.session.closed:
                _LOGGER.error(f"Could not create session for {self.api.__class__.__name__}")
                return None

            # Format the date consistently
            if isinstance(date, datetime.datetime):
                date_str = date.strftime("%Y-%m-%d")
            else:
                date_str = date

            # Store current configuration
            self.api._area = area
            self.api._currency = currency
            self.api._date_str = date_str

            # Generate cache key
            cache_key = f"{self.api.__class__.__name__}_{area}_{currency}_{date_str}"

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
            self.api._last_fetched = current_time

            # Fetch the raw data
            _LOGGER.debug(f"Fetching data for {area} on {date_str} with currency {currency}")
            raw_data = await self.api._fetch_data()

            if raw_data:
                _LOGGER.debug(f"API {self.api.__class__.__name__} raw response received")

            if not raw_data:
                _LOGGER.error(f"No data received from API for {area} on {date_str}")
                return None

            # Process the data into a consistent format
            _LOGGER.debug(f"Processing raw data for {area}")
            processed_data = await self.api._process_data(raw_data)

            if processed_data:
                # Log the raw API response but don't store it in processed data
                if "raw_api_response" in processed_data:
                    _LOGGER.debug(
                        "Raw API response for %s: %s bytes of data",
                        self.api.__class__.__name__,
                        len(str(processed_data["raw_api_response"]))
                    )
                    # Remove raw API response to prevent attribute size issues
                    processed_data.pop("raw_api_response", None)

                # Add source information
                processed_data["data_source"] = self.api.__class__.__name__

                # Add raw values to processed data
                if "raw_values" not in processed_data:
                    processed_data["raw_values"] = {}

                # Include Home Assistant timezone information
                if self.api.hass:
                    processed_data["ha_timezone"] = str(self.api.hass.config.time_zone)

                # Log conversions for debugging
                self._log_conversions(processed_data)

                # Mark as successful fetch
                self._last_successful_fetch = processed_data
                self.api._last_successful_fetch = processed_data

                # Cache the result
                self._cache[cache_key] = {
                    'data': processed_data,
                    'timestamp': current_time
                }
                
                # Update API's cache too
                self.api._cache[cache_key] = self._cache[cache_key]

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
        _LOGGER.debug(f"Value conversions for {self.api.__class__.__name__}:")

        for key in ["current_price", "next_hour_price", "day_average_price", "peak_price", "off_peak_price"]:
            if key in processed_data and "raw_values" in processed_data and key in processed_data["raw_values"]:
                raw_info = processed_data["raw_values"][key]
                if isinstance(raw_info, dict) and "raw" in raw_info:
                    raw = raw_info["raw"]
                    converted = processed_data[key]
                    _LOGGER.debug(f"  - {key}: {raw} → {converted} (applied VAT {self.api.vat:.2%})")

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

    async def fetch_with_retry(self, url, params=None, headers=None, timeout=30, max_retries=3):
        """Fetch data from URL with retry mechanism."""
        return await fetch_with_retry(self.api, url, params, headers, timeout, max_retries)
