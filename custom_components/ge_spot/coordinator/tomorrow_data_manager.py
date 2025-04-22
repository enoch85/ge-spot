"""Tomorrow data manager for electricity spot prices."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List, Tuple, Union, Callable, Awaitable

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..price import ElectricityPriceAdapter
from ..const.config import Config
from ..const.sources import Source
from ..const.defaults import Defaults
from ..const.display import DisplayUnit
from ..const.network import Network
from ..utils.fallback import FallbackManager
from ..utils.price_extractor import extract_prices, get_timestamp_date

_LOGGER = logging.getLogger(__name__)

class TomorrowDataManager:
    """Manager for searching and retrieving tomorrow's price data."""

    def __init__(
        self,
        hass: HomeAssistant,
        area: str,
        currency: str,
        config: Dict[str, Any],
        price_cache: Any,
        tz_service: Any,
        session: Optional[Any] = None,
        refresh_callback: Optional[Callable] = None
    ):
        """Initialize the tomorrow data manager.

        Args:
            hass: Home Assistant instance
            area: Area code
            currency: Currency code
            config: Configuration dictionary
            price_cache: Price cache instance
            tz_service: Timezone service instance
            session: Optional session for API requests
        """
        self.hass = hass
        self.area = area
        self.currency = currency
        self.config = config
        self._price_cache = price_cache
        self._tz_service = tz_service
        self.session = session
        self._refresh_callback = refresh_callback

        # Tomorrow data search tracking
        self._search_active = False
        self._last_attempt = None
        self._attempt_count = 0
        self._search_end_time = None
        self._use_subunit = config.get(Config.DISPLAY_UNIT) == DisplayUnit.CENTS

        # Data tracking
        self._last_successful_data = None
        self._has_tomorrow_data = False

    def should_search(self, now: datetime) -> bool:
        """Determine if we should search for tomorrow's data.

        Args:
            now: Current datetime

        Returns:
            True if we should search for tomorrow's data
        """
        # Always check if we already have tomorrow's data first
        if self._check_if_has_tomorrow_data():
            _LOGGER.debug("Already have tomorrow's data, no need to search")
            return False

        # Reset search at midnight
        if now.hour == 0 and now.minute < 15:
            if self._search_active:
                _LOGGER.info("Resetting tomorrow data search at midnight")
                self._search_active = False
                self._attempt_count = 0
                self._last_attempt = None
                self._search_end_time = None
            return False

        # Stop searching as we approach midnight
        if now.hour >= 23 and now.minute >= 45:
            if self._search_active:
                _LOGGER.info("Approaching midnight, ending tomorrow data search")
                self._search_active = False
            return False


        # If we're past 13:00, start/continue active search with exponential backoff
        if now.hour >= 13:
            # If we haven't started searching yet, start now
            if not self._search_active:
                _LOGGER.info(f"Starting search for tomorrow's data (current hour: {now.hour}:00)")
                self._search_active = True
                self._attempt_count = 0
                self._last_attempt = None
                self._search_end_time = now.replace(hour=23, minute=45, second=0, microsecond=0)
                return True

            # If we're already searching, check if it's time for the next attempt
            if self._last_attempt:
                # Calculate time since last attempt
                time_since_attempt = (now - self._last_attempt).total_seconds() / 60

                # Calculate wait time based on exponential backoff
                wait_time = self.calculate_wait_time()

                # If enough time has passed, try again
                if time_since_attempt >= wait_time:
                    _LOGGER.debug(f"Time since last attempt ({time_since_attempt:.1f} min) >= wait time ({wait_time:.1f} min), trying again")
                    return True
                else:
                    _LOGGER.debug(f"Not enough time since last attempt ({time_since_attempt:.1f} min < {wait_time:.1f} min), waiting")
                    return False

            # First attempt after starting search
            return True

        # Before 13:00, don't actively search (but we'll still check during regular updates)
        _LOGGER.debug(f"Before start time for tomorrow's data search, current hour: {now.hour}:00")
        return False

    def _check_if_has_tomorrow_data(self) -> bool:
        """Check if we already have tomorrow's data.

        Returns:
            True if we have tomorrow's data
        """
        # First check our internal tracking
        if self._has_tomorrow_data:
            _LOGGER.debug("Internal tracking indicates we have tomorrow's data")
            return True

        # Then check if we have last_successful_data with tomorrow_valid
        if self._last_successful_data and self._last_successful_data.get("tomorrow_valid", False):
            _LOGGER.debug("Last successful data indicates we have tomorrow's data")
            return True

        # Check if tomorrow's data is in the cache
        try:
            # Get tomorrow's date
            tomorrow = dt_util.now().date() + timedelta(days=1)
            tomorrow_str = tomorrow.strftime("%Y-%m-%d")

            # Check if we have data for tomorrow in the cache
            if hasattr(self._price_cache, "_cache") and self.area in self._price_cache._cache:
                # First check tomorrow's data in its own date entry
                if tomorrow_str in self._price_cache._cache[self.area]:
                    # We have data for tomorrow in the cache
                    for source, data in self._price_cache._cache[self.area][tomorrow_str].items():
                        if "hourly_prices" in data:
                            # Log detailed info about how many hours we found
                            _LOGGER.info(f"Found tomorrow's data in cache for source {source}: {len(data['hourly_prices'])} hours")

                            # Update our tracking variables
                            self._has_tomorrow_data = True

                            # Create adapter to validate the data
                            adapter = ElectricityPriceAdapter(self.hass, [data], source, self._use_subunit)
                            if adapter.is_tomorrow_valid():
                                _LOGGER.info("Tomorrow's data in cache is valid")
                                return True
                            else:
                                _LOGGER.info(f"Tomorrow's data in cache contains {len(data['hourly_prices'])} hours but validation failed - needs at least 12 hours")

                # Check if we have tomorrow's data in today's cache
                today_str = dt_util.now().date().strftime("%Y-%m-%d")
                if today_str in self._price_cache._cache[self.area]:
                    # We have data for today in the cache
                    for source, data in self._price_cache._cache[self.area][today_str].items():
                        # Check various possible formats for tomorrow data
                        found_tomorrow_data = False
                        tomorrow_hours_count = 0

                        # Check for tomorrow_hourly_prices format
                        if "tomorrow_hourly_prices" in data:
                            tomorrow_hours_count = len(data["tomorrow_hourly_prices"])
                            found_tomorrow_data = True
                            _LOGGER.info(f"Found tomorrow_hourly_prices in today's cache for source {source}: {tomorrow_hours_count} hours")

                        # Check for hourly_prices with ISO timestamps
                        elif "hourly_prices" in data:
                            # Extract hourly prices and categorize them
                            hourly_prices = data.get("hourly_prices", {})
                            if hourly_prices:
                                # Get the user's timezone from the timezone service
                                user_timezone = self._tz_service.ha_timezone
                                
                                # Manually categorize hourly prices into tomorrow
                                tomorrow_hours = {}
                                tomorrow = dt_util.now().date() + timedelta(days=1)
                                
                                # Count tomorrow hours
                                for timestamp_str, price in hourly_prices.items():
                                    dt = get_timestamp_date(timestamp_str, user_timezone)
                                    if dt and dt.date() == tomorrow:
                                        hour_key = f"{dt.hour:02d}:00"
                                        tomorrow_hours[hour_key] = price
                                
                                # Check if we have tomorrow prices
                                if tomorrow_hours:
                                    tomorrow_hours_count = len(tomorrow_hours)
                                    found_tomorrow_data = True
                                    _LOGGER.info(f"Found {tomorrow_hours_count} hours of tomorrow's data within hourly_prices in today's cache for source {source}")

                        if found_tomorrow_data:
                            # Update our tracking variables
                            self._has_tomorrow_data = True

                            # Create adapter to validate the data
                            adapter = ElectricityPriceAdapter(self.hass, [data], source, self._use_subunit)
                            if adapter.is_tomorrow_valid():
                                _LOGGER.info(f"Tomorrow's data in today's cache is valid with {tomorrow_hours_count} hours")
                                return True
                            else:
                                _LOGGER.info(f"Tomorrow's data in today's cache contains {tomorrow_hours_count} hours but validation failed - needs at least 12 hours")
        except Exception as e:
            _LOGGER.error(f"Error checking cache for tomorrow's data: {e}")
            import traceback
            _LOGGER.debug(f"Traceback: {traceback.format_exc()}")

        return False

    def update_data_status(self, last_successful_data: Optional[Dict[str, Any]] = None) -> None:
        """Update the data status with the latest information.

        Args:
            last_successful_data: The latest successful data from the coordinator
        """
        self._last_successful_data = last_successful_data

        # Update our internal tracking of tomorrow data status
        if last_successful_data and last_successful_data.get("tomorrow_valid", False):
            self._has_tomorrow_data = True
        else:
            # Only set to False if we don't have data - don't override True
            # This ensures we don't lose track of tomorrow data we found ourselves
            if not self._has_tomorrow_data:
                self._has_tomorrow_data = False

    def calculate_wait_time(self) -> float:
        """Calculate wait time for next tomorrow data attempt using exponential backoff.

        Returns:
            Wait time in minutes
        """
        # Start with initial retry time
        initial_retry = Defaults.TOMORROW_DATA_INITIAL_RETRY_MINUTES

        # Apply exponential backoff
        if self._attempt_count == 0:
            return initial_retry

        backoff_factor = Defaults.TOMORROW_DATA_BACKOFF_FACTOR
        max_retries = Defaults.TOMORROW_DATA_MAX_RETRIES

        # Cap at max retries
        attempt = min(self._attempt_count, max_retries)

        # Calculate wait time with exponential backoff
        wait_time = initial_retry * (backoff_factor ** (attempt - 1))

        # Cap at 3 hours
        return min(wait_time, 180)

    async def fetch_data(self) -> bool:
        """Fetch tomorrow's data specifically.

        Returns:
            True if tomorrow's data was found
        """
        # Check if we already have tomorrow's data
        if self._check_if_has_tomorrow_data():
            _LOGGER.debug("Already have tomorrow's data, skipping fetch")
            return True

        # Check rate limiter before proceeding
        current_time = dt_util.now()
        from ..utils.rate_limiter import RateLimiter
        should_skip, skip_reason = RateLimiter.should_skip_fetch(
            last_fetched=self._last_attempt,
            current_time=current_time,
            consecutive_failures=0,  # We track our own failures
            min_interval=Defaults.TOMORROW_DATA_INITIAL_RETRY_MINUTES
        )

        if should_skip:
            _LOGGER.debug(f"Rate limiter suggests skipping tomorrow data fetch: {skip_reason}")
            return False

        _LOGGER.info(f"Attempting to fetch tomorrow's data (attempt {self._attempt_count + 1})")

        # Update attempt tracking
        self._attempt_count += 1
        self._last_attempt = dt_util.now()

        # Use FallbackManager to try all sources in parallel
        fallback_mgr = FallbackManager(
            hass=self.hass,
            config=self.config,
            area=self.area,
            currency=self.currency,
            session=self.session
        )

        # Try to fetch data from all sources
        result = await fallback_mgr.fetch_with_fallbacks()

        # If we got data, process it to extract tomorrow's data
        if result["data"]:
            # Extract hourly prices using our generic extractor
            hourly_prices = result["data"].get("hourly_prices", {})
            if not hourly_prices:
                # If hourly_prices not already extracted, extract them now
                hourly_prices = extract_prices(result["data"], self.area)
                
            # If we have hourly prices, categorize them into today and tomorrow
            if hourly_prices:
                # Get the user's timezone from the timezone service
                user_timezone = self._tz_service.ha_timezone
                
                # Categorize hourly prices into today and tomorrow
                tomorrow_hourly_prices = {}
                tomorrow = dt_util.now().date() + timedelta(days=1)
                
                # Manually categorize hourly prices
                for timestamp_str, price in hourly_prices.items():
                    dt = get_timestamp_date(timestamp_str, user_timezone)
                    if dt and dt.date() == tomorrow:
                        hour_key = f"{dt.hour:02d}:00"
                        tomorrow_hourly_prices[hour_key] = price
                
                # Check if we have tomorrow prices with at least 12 hours
                if tomorrow_hourly_prices and len(tomorrow_hourly_prices) >= 12:
                    _LOGGER.info(f"Found valid tomorrow data from {result['source']} with {len(tomorrow_hourly_prices)} hours")
                    
                    # Create processed data
                    processed_data = {
                        "data_source": result["source"],
                        "currency": result["data"].get("currency", self.currency),  # Use API's currency if available
                        "api_timezone": result["data"].get("api_timezone", "UTC"),  # Use API's timezone if available
                        "hourly_prices": hourly_prices,
                        "raw_data": result["data"].get("raw_data", {})  # Keep the raw data for reference
                    }
                    
                    # Copy any other metadata from the original data
                    for key, value in result["data"].items():
                        if key not in ["raw_data", "hourly_prices", "currency", "api_timezone"]:
                            processed_data[key] = value

                    # Store the data in cache
                    self._price_cache.store(processed_data, self.area, result["source"], dt_util.now())

                    # Update our tracking variables
                    self._search_active = False
                    self._has_tomorrow_data = True

                    # Force a regular update to use the new data
                    await self._request_refresh_callback()

                    return True
                else:
                    _LOGGER.info(f"Source {result['source']} returned data but no valid tomorrow data (found {len(tomorrow_hourly_prices)} hours, need at least 12)")

                    # Try fallback sources if available
                    for fb_source in result.get("fallback_sources", []):
                        if fb_source != result["source"] and f"fallback_data_{fb_source}" in result:
                            fb_data = result[f"fallback_data_{fb_source}"]
                            
                            # Extract hourly prices from fallback data
                            fb_hourly_prices = fb_data.get("hourly_prices", {})
                            if not fb_hourly_prices:
                                fb_hourly_prices = extract_prices(fb_data, self.area)
                                
                            # If we have hourly prices, categorize them
                            if fb_hourly_prices:
                                # Categorize hourly prices into today and tomorrow
                                fb_tomorrow_hourly_prices = {}
                                tomorrow = dt_util.now().date() + timedelta(days=1)
                                
                                # Manually categorize hourly prices
                                for timestamp_str, price in fb_hourly_prices.items():
                                    dt = get_timestamp_date(timestamp_str, user_timezone)
                                    if dt and dt.date() == tomorrow:
                                        hour_key = f"{dt.hour:02d}:00"
                                        fb_tomorrow_hourly_prices[hour_key] = price
                                
                                # Check if we have tomorrow prices with at least 12 hours
                                if fb_tomorrow_hourly_prices and len(fb_tomorrow_hourly_prices) >= 12:
                                    _LOGGER.info(f"Found valid tomorrow data from fallback source {fb_source} with {len(fb_tomorrow_hourly_prices)} hours")
                                    
                                    # Create processed data
                                    fb_processed_data = {
                                        "data_source": fb_source,
                                        "currency": fb_data.get("currency", self.currency),  # Use API's currency if available
                                        "api_timezone": fb_data.get("api_timezone", "UTC"),  # Use API's timezone if available
                                        "hourly_prices": fb_hourly_prices,
                                        "raw_data": fb_data.get("raw_data", {})  # Keep the raw data for reference
                                    }
                                    
                                    # Copy any other metadata from the original data
                                    for key, value in fb_data.items():
                                        if key not in ["raw_data", "hourly_prices", "currency", "api_timezone"]:
                                            fb_processed_data[key] = value

                                    # Store the fallback data in cache
                                    self._price_cache.store(fb_processed_data, self.area, fb_source, dt_util.now())

                                    # Update our tracking variables
                                    self._search_active = False
                                    self._has_tomorrow_data = True

                                    # Force a regular update to use the new data
                                    await self._request_refresh_callback()

                                    return True

        # If we reach here, we didn't find tomorrow's data
        _LOGGER.info(f"No tomorrow data found, will try again in {self.calculate_wait_time():.1f} minutes")
        return False

    async def _request_refresh_callback(self):
        """Callback to request a refresh from the coordinator."""
        if self._refresh_callback:
            # Set last_api_fetch to None to force a refresh
            await self._refresh_callback()
            _LOGGER.debug("Requested refresh from coordinator after finding tomorrow's data")
        else:
            _LOGGER.warning("No refresh callback provided, cannot request refresh")

    def get_status(self) -> Dict[str, Any]:
        """Get current status of tomorrow data search.

        Returns:
            Dictionary with status information
        """
        next_attempt = None
        if self._search_active and self._last_attempt:
            wait_time = self.calculate_wait_time()
            next_attempt = self._last_attempt + timedelta(minutes=wait_time)

        return {
            "search_active": self._search_active,
            "attempt_count": self._attempt_count,
            "last_attempt": self._last_attempt.isoformat() if self._last_attempt else None,
            "next_attempt": next_attempt.isoformat() if next_attempt else None
        }
