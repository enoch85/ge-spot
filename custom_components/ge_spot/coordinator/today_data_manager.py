"""Today data manager for electricity spot prices."""
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
from ..utils.fallback import FallbackManager

_LOGGER = logging.getLogger(__name__)

class TodayDataManager:
    """Manager for fetching and processing today's price data."""

    def __init__(
        self,
        hass: HomeAssistant,
        area: str,
        currency: str,
        config: Dict[str, Any],
        price_cache: Any,
        tz_service: Any,
        session: Optional[Any] = None
    ):
        """Initialize the today data manager.

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

        # API source tracking
        self._active_source = None
        self._attempted_sources = []
        self._fallback_data = {}
        self._use_subunit = config.get(Config.DISPLAY_UNIT) == DisplayUnit.CENTS

        # API fetch tracking
        self._last_api_fetch = None
        self._next_scheduled_api_fetch = None
        self._consecutive_failures = 0
        self._last_failure_time = None

    async def fetch_data(self, reason: str) -> Dict[str, Any]:
        """Fetch today's price data from APIs.

        Args:
            reason: Reason for fetching data

        Returns:
            Dictionary with fetched data and metadata, or empty dict with error info if all sources failed
        """
        _LOGGER.info(f"Fetching new data from API for {self.area} - Reason: {reason}")

        # Reset tracking
        self._active_source = None
        self._attempted_sources = []
        self._fallback_data = {}

        # Use FallbackManager to handle API fetches with automatic fallbacks
        fallback_mgr = FallbackManager(
            hass=self.hass,
            config=self.config,
            area=self.area,
            currency=self.currency,
            session=self.session
        )

        # Try to fetch data from all sources
        result = await fallback_mgr.fetch_with_fallbacks()
        
        # Initialize a default response dictionary with empty values
        response = {
            "data": None,
            "source": None,
            "attempted_sources": [],
            "skipped_sources": [],
            "fallback_sources": []
        }
        
        # If all sources failed or were skipped
        if not result or not result.get("data"):
            # Check if we have skipped sources
            skipped_sources = result.get("skipped_sources", []) if result else []
            if skipped_sources:
                _LOGGER.info(f"Some sources were skipped for area {self.area}: {skipped_sources}")
                _LOGGER.info(f"This is usually due to missing API keys for those sources.")
                response["skipped_sources"] = skipped_sources

            # Count as a failure
            self._consecutive_failures += 1
            self._last_failure_time = dt_util.now()
            _LOGGER.error(f"Failed to fetch data from any source for area {self.area}")

            return response

        # Use the successful data
        data = result["data"]
        self._active_source = result["source"]
        self._attempted_sources = result.get("attempted_sources", [])
        self._consecutive_failures = 0

        # Update response with result data
        response.update({
            "data": data,
            "source": self._active_source,
            "active_source": self._active_source,
            "attempted_sources": self._attempted_sources,
            "skipped_sources": result.get("skipped_sources", []),
            "fallback_sources": result.get("fallback_sources", [])
        })

        # Store fallback data if available
        for fb_source in result.get("fallback_sources", []):
            if fb_source != result["source"] and f"fallback_data_{fb_source}" in result:
                self._fallback_data[fb_source] = result[f"fallback_data_{fb_source}"]
                # Add fallback data to response
                response[f"fallback_data_{fb_source}"] = result[f"fallback_data_{fb_source}"]

        # Process the raw data to extract today's and tomorrow's prices
        processed_data = self._process_raw_data(data, self._active_source)
        
        # Store in cache
        self._price_cache.store(processed_data, self.area, result["source"], dt_util.now())

        # Update tracker variables for timestamps
        self._last_api_fetch = dt_util.now()

        # Update the response with the processed data
        response["data"] = processed_data

        return response
        
    def _process_raw_data(self, data: Dict[str, Any], source: str) -> Dict[str, Any]:
        """Process raw data from API to extract today's and tomorrow's prices.
        
        Args:
            data: Raw data from API
            source: Source of the data
            
        Returns:
            Processed data with today's and tomorrow's prices
        """
        # Initialize result with basic metadata
        result = {
            "data_source": source,
            "currency": self.currency,
            "today_hourly_prices": {},
            "tomorrow_hourly_prices": {}
        }
        
        # Extract raw data
        raw_data = data.get("raw_data", data)
        
        # Check if we have today and tomorrow data in the combined format
        if isinstance(raw_data, dict) and "today" in raw_data and "tomorrow" in raw_data:
            today_data = raw_data["today"]
            tomorrow_data = raw_data["tomorrow"]
            
            # Process today's data
            if isinstance(today_data, dict) and "multiAreaEntries" in today_data:
                today_entries = today_data["multiAreaEntries"]
                self._extract_hourly_prices(today_entries, result["today_hourly_prices"], is_tomorrow=False)
            
            # Process tomorrow's data
            if isinstance(tomorrow_data, dict) and "multiAreaEntries" in tomorrow_data:
                tomorrow_entries = tomorrow_data["multiAreaEntries"]
                self._extract_hourly_prices(tomorrow_entries, result["tomorrow_hourly_prices"], is_tomorrow=True)
        else:
            # If not in combined format, process as today's data
            if isinstance(raw_data, dict) and "multiAreaEntries" in raw_data:
                today_entries = raw_data["multiAreaEntries"]
                self._extract_hourly_prices(today_entries, result["today_hourly_prices"], is_tomorrow=False)
        
        # Add API timezone if available
        if "api_timezone" in data:
            result["api_timezone"] = data["api_timezone"]
        
        # Copy any other metadata from the original data
        for key, value in data.items():
            if key not in ["raw_data", "today_hourly_prices", "tomorrow_hourly_prices"]:
                result[key] = value
        
        return result
    
    def _extract_hourly_prices(self, entries: List[Dict[str, Any]], target_dict: Dict[str, float], is_tomorrow: bool = False):
        """Extract hourly prices from entries and add them to the target dictionary.
        
        Args:
            entries: List of entries from API
            target_dict: Dictionary to add prices to
            is_tomorrow: Whether these entries are for tomorrow
        """
        from datetime import datetime, timezone, timedelta
        
        # Get today's and tomorrow's dates
        today = datetime.now(timezone.utc).date()
        tomorrow = today + timedelta(days=1)
        
        # Process each entry
        for entry in entries:
            if not isinstance(entry, dict) or "entryPerArea" not in entry:
                continue
                
            if self.area not in entry["entryPerArea"]:
                continue
                
            # Extract values
            start_time = entry.get("deliveryStart")
            raw_price = entry["entryPerArea"][self.area]
            
            if start_time and raw_price is not None:
                try:
                    # Parse timestamp
                    dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    
                    # Check if this entry is for today or tomorrow
                    entry_date = dt.date()
                    if (is_tomorrow and entry_date == tomorrow) or (not is_tomorrow and entry_date == today):
                        # Format as simple hour key
                        hour_key = f"{dt.hour:02d}:00"
                        target_dict[hour_key] = float(raw_price)
                except (ValueError, TypeError) as e:
                    _LOGGER.warning(f"Failed to parse timestamp: {start_time} - {e}")

    def get_adapters(self, data: Dict[str, Any]) -> Tuple[ElectricityPriceAdapter, Dict[str, ElectricityPriceAdapter]]:
        """Create adapters for primary and fallback sources.

        Args:
            data: Data from fetch_data

        Returns:
            Tuple of (primary_adapter, fallback_adapters)
        """
        # Create adapter for primary source
        primary_adapter = ElectricityPriceAdapter(
            self.hass, [data], self._active_source, self._use_subunit
        )

        # Create adapters for fallback sources
        fallback_adapters = {}
        for src, fb_data in self._fallback_data.items():
            fallback_adapters[src] = ElectricityPriceAdapter(
                self.hass, [fb_data], src, self._use_subunit
            )

        return primary_adapter, fallback_adapters

    def has_current_hour_price(self) -> bool:
        """Check if cache has current hour price.

        Returns:
            True if cache has current hour price
        """
        return self._price_cache.has_current_hour_price(self.area)

    def get_current_hour_price(self) -> Dict[str, Any]:
        """Get current hour price from cache.

        Returns:
            Dictionary with current hour price data
        """
        return self._price_cache.get_current_hour_price(self.area)

    def get_cached_data(self) -> Dict[str, Any]:
        """Get data from cache.

        Returns:
            Dictionary with cached data
        """
        return self._price_cache.get_data(self.area)

    def get_status(self) -> Dict[str, Any]:
        """Get current status of today data fetching.

        Returns:
            Dictionary with status information
        """
        return {
            "active_source": self._active_source,
            "attempted_sources": self._attempted_sources,
            "fallback_sources": list(self._fallback_data.keys()),
            "last_api_fetch": self._last_api_fetch.isoformat() if self._last_api_fetch else None,
            "next_scheduled_api_fetch": self._next_scheduled_api_fetch.isoformat() if self._next_scheduled_api_fetch else None,
            "consecutive_failures": self._consecutive_failures,
            "last_failure_time": self._last_failure_time.isoformat() if self._last_failure_time else None
        }
