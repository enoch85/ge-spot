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
        # Reset search at midnight
        if now.hour == 0 and now.minute < 15:
            if self._search_active:
                _LOGGER.info("Resetting tomorrow data search at midnight")
                self._search_active = False
                self._attempt_count = 0
                self._last_attempt = None
                self._search_end_time = None
            return False

        # Check if we're in or past the special window for tomorrow's data (13:00-14:00)
        in_special_window = False
        past_special_window = False
        for start_hour, end_hour in Network.Defaults.SPECIAL_HOUR_WINDOWS:
            if start_hour == 13:
                if start_hour <= now.hour < end_hour:
                    in_special_window = True
                    _LOGGER.debug(f"In special window for tomorrow's data: {start_hour}:00-{end_hour}:00, current hour: {now.hour}:00")
                    break
                elif now.hour >= end_hour:
                    past_special_window = True
                    _LOGGER.debug(f"Past special window for tomorrow's data: {start_hour}:00-{end_hour}:00, current hour: {now.hour}:00")
                    break

        # If we're in the special window, we should search
        if in_special_window:
            _LOGGER.info(f"In special window for tomorrow's data: 13:00-14:00, current hour: {now.hour}:00")
            return True
        
        # If we're not past the special window, don't search
        if not past_special_window:
            _LOGGER.debug(f"Not past special window for tomorrow's data yet, current hour: {now.hour}:00")
            return False

        # If we already have tomorrow's data, don't search
        has_tomorrow_data = self._check_if_has_tomorrow_data()
        if has_tomorrow_data:
            # If search was active, log that we found tomorrow's data
            if self._search_active:
                _LOGGER.info("Found tomorrow's data, ending search")
                self._search_active = False
                self._attempt_count = 0
            _LOGGER.debug("Already have tomorrow's data, no need to search")
            return False

        # If we're past 23:59, don't search (we'll get it as today's data after midnight)
        if now.hour >= 23 and now.minute >= 45:
            if self._search_active:
                _LOGGER.info("Approaching midnight, ending tomorrow data search")
                self._search_active = False
            return False

        # If we haven't started searching yet, start now
        if not self._search_active:
            _LOGGER.info(f"Starting search for tomorrow's data after special window (current hour: {now.hour}:00)")
            self._search_active = True
            self._attempt_count = 0
            self._last_attempt = None

            # Set end time to 23:45 today
            end_time = now.replace(hour=23, minute=45, second=0, microsecond=0)
            self._search_end_time = end_time
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

    def _check_if_has_tomorrow_data(self) -> bool:
        """Check if we already have tomorrow's data.

        Returns:
            True if we have tomorrow's data
        """
        # First check our internal tracking
        if self._has_tomorrow_data:
            return True

        # Then check if we have last_successful_data with tomorrow_valid
        if self._last_successful_data and self._last_successful_data.get("tomorrow_valid", False):
            return True

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
        _LOGGER.info(f"Attempting to fetch tomorrow's data (attempt {self._attempt_count + 1})")

        # Update attempt tracking
        self._attempt_count += 1
        self._last_attempt = dt_util.now()

        # Use FallbackManager to try all sources
        fallback_mgr = FallbackManager(
            hass=self.hass,
            config=self.config,
            area=self.area,
            currency=self.currency,
            session=self.session
        )

        # Try to fetch data from all sources
        result = await fallback_mgr.fetch_with_fallbacks()

        # If we got data, check if it has tomorrow's data
        if result["data"]:
            data = result["data"]

            # Create adapter to check if tomorrow data is valid
            adapter = ElectricityPriceAdapter(self.hass, [data], self._use_subunit)
            has_tomorrow_data = adapter.is_tomorrow_valid()

            if has_tomorrow_data:
                _LOGGER.info(f"Successfully found tomorrow's data from {result['source']}")

                # Store the data in cache
                self._price_cache.store(data, self.area, result["source"], dt_util.now())

                # Update our tracking variables
                self._search_active = False
                self._has_tomorrow_data = True

                # Force a regular update to use the new data
                # This requires access to the coordinator's async_request_refresh method
                # We'll need to handle this differently or pass a callback
                await self._request_refresh_callback()

                return True
            else:
                _LOGGER.info(f"Source {result['source']} returned data but no valid tomorrow data")

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
