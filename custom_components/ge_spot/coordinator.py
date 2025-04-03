"""Data update coordinator for electricity spot prices."""
import logging
from datetime import timedelta
from typing import Any, Dict, Optional, List
import datetime

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .price_adapter import ElectricityPriceAdapter
from .const import (
    Attributes,
    ATTR_CURRENT_PRICE,
    ATTR_TODAY,
    ATTR_TOMORROW,
    ATTR_RAW_TODAY,
    ATTR_RAW_TOMORROW,
    ATTR_TOMORROW_VALID,
    ATTR_LAST_UPDATED,
    ATTR_DATA_SOURCE,
    ATTR_FALLBACK_USED,
    ATTR_RAW_API_DATA,
    CONF_ENABLE_FALLBACK,
    DEFAULT_ENABLE_FALLBACK,
)

_LOGGER = logging.getLogger(__name__)

class ElectricityPriceCoordinator(DataUpdateCoordinator):
    """Data update coordinator for electricity prices."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        update_interval: timedelta,
        api: Any,
        area: str,
        currency: str,
        fallback_apis: List[Any] = None,
        enable_fallback: bool = DEFAULT_ENABLE_FALLBACK,
    ):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=update_interval,
        )
        self.api = api
        self.area = area
        self.currency = currency
        self.adapter = None
        self._last_successful_data = None
        self._fallback_apis = fallback_apis or []
        self._enable_fallback = enable_fallback
        self._active_source = api.__class__.__name__ if api else None
        self._fallback_used = False
        self._attempted_sources = []  # Track all sources that were attempted

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            _LOGGER.info(f"Updating data for area {self.area} with currency {self.currency}")

            # Reset tracking variables
            self._fallback_used = False
            self._active_source = self.api.__class__.__name__ if self.api else None
            self._attempted_sources = [self._active_source] if self._active_source else []

            # Fetch today's data from primary source
            _LOGGER.info(f"Attempting to fetch data from primary source: {self._active_source}")
            today_data = None

            if self.api:
                today_data = await self.api.fetch_day_ahead_prices(
                    self.area,
                    self.currency,
                    dt_util.now()
                )

            # If primary API failed and fallback is enabled, try fallback APIs
            if not today_data and self._enable_fallback and self._fallback_apis:
                _LOGGER.info("Primary API failed, attempting fallback sources")
                for fallback_api in self._fallback_apis:
                    fallback_name = fallback_api.__class__.__name__
                    _LOGGER.info(f"Trying fallback API: {fallback_name}")
                    self._fallback_used = True
                    self._active_source = fallback_name
                    self._attempted_sources.append(fallback_name)

                    today_data = await fallback_api.fetch_day_ahead_prices(
                        self.area,
                        self.currency,
                        dt_util.now()
                    )

                    if today_data:
                        _LOGGER.info(f"Successfully retrieved data from fallback API: {fallback_name}")
                        break

            if not today_data:
                _LOGGER.error(f"Failed to fetch today's price data from any source. Attempted: {', '.join(self._attempted_sources)}")
                if self._last_successful_data:
                    _LOGGER.warning("Using cached data from last successful update")
                    self._last_successful_data[ATTR_FALLBACK_USED] = True
                    self._last_successful_data["fallback_info"] = {
                        "reason": "All API sources failed",
                        "attempted_sources": self._attempted_sources,
                        "using_cached_data": True,
                        "cache_timestamp": self._last_successful_data.get(ATTR_LAST_UPDATED, "unknown")
                    }
                    return self._last_successful_data
                return None

            # Try to fetch tomorrow's data if after 1 PM
            tomorrow_data = None
            tomorrow_source = None
            now = dt_util.as_local(dt_util.now())
            tomorrow_attempted_sources = []

            if now.hour >= 13:
                try:
                    # First try from the same source that provided today's data
                    api_to_use = None
                    if self._fallback_used:
                        # We already used a fallback API for today's data, use the same for tomorrow
                        for fallback_api in self._fallback_apis:
                            if fallback_api.__class__.__name__ == self._active_source:
                                api_to_use = fallback_api
                                break
                    else:
                        # Use primary API for tomorrow's data
                        api_to_use = self.api

                    if api_to_use:
                        tomorrow_source = api_to_use.__class__.__name__
                        tomorrow_attempted_sources.append(tomorrow_source)
                        _LOGGER.info(f"Attempting to fetch tomorrow's data from same source: {tomorrow_source}")
                        tomorrow_data = await api_to_use.fetch_day_ahead_prices(
                            self.area,
                            self.currency,
                            dt_util.now() + timedelta(days=1)
                        )

                    if tomorrow_data:
                        _LOGGER.info(f"Successfully fetched tomorrow's price data from {tomorrow_source}")
                    else:
                        _LOGGER.warning(f"Tomorrow's price data not available from {tomorrow_source}")

                        # If primary source failed for tomorrow's data, try fallbacks
                        if self._enable_fallback and self._fallback_apis:
                            for fallback_api in self._fallback_apis:
                                fallback_name = fallback_api.__class__.__name__
                                if fallback_name != self._active_source:  # Don't retry the same fallback
                                    _LOGGER.info(f"Trying fallback API for tomorrow's data: {fallback_name}")
                                    tomorrow_attempted_sources.append(fallback_name)

                                    tomorrow_data = await fallback_api.fetch_day_ahead_prices(
                                        self.area,
                                        self.currency,
                                        dt_util.now() + timedelta(days=1)
                                    )

                                    if tomorrow_data:
                                        tomorrow_source = fallback_name
                                        _LOGGER.info(f"Successfully retrieved tomorrow's data from fallback API: {tomorrow_source}")
                                        break
                except Exception as err:
                    _LOGGER.warning(f"Failed to fetch tomorrow's prices: {err}")
            else:
                _LOGGER.info(f"Not fetching tomorrow's data yet, current hour: {now.hour}")

            # Combine the data
            all_data = []
            if today_data:
                all_data.append(today_data)
            if tomorrow_data:
                all_data.append(tomorrow_data)

            # Extract raw API data for logging (not storing in attributes)
            if "raw_api_response" in today_data:
                _LOGGER.debug(
                    "Raw API response for today (%s): %s bytes of data",
                    self._active_source,
                    len(str(today_data["raw_api_response"]))
                )
                # Remove raw API response to prevent attribute size issues
                today_data.pop("raw_api_response", None)

            if tomorrow_data and "raw_api_response" in tomorrow_data:
                _LOGGER.debug(
                    "Raw API response for tomorrow (%s): %s bytes of data",
                    tomorrow_source,
                    len(str(tomorrow_data["raw_api_response"]))
                )
                # Remove raw API response to prevent attribute size issues
                tomorrow_data.pop("raw_api_response", None)

            # Create adapter with processed data
            _LOGGER.info("Creating price adapter with fetched data")
            self.adapter = ElectricityPriceAdapter(self.hass, all_data)

            if not self.adapter:
                _LOGGER.error("Failed to create price adapter")
                if self._last_successful_data:
                    return self._last_successful_data
                return None

            # Process statistics for today
            today_stats = {
                "min": None,
                "max": None,
                "average": None,
                "off_peak_1": None,
                "off_peak_2": None,
                "peak": None
            }

            today_prices = self.adapter.get_today_prices()
            if today_prices:
                today_stats = {
                    "min": min(today_prices) if today_prices else None,
                    "max": max(today_prices) if today_prices else None,
                    "average": sum(today_prices) / len(today_prices) if today_prices else None,
                    "off_peak_1": None,  # These would be calculated properly in a real implementation
                    "off_peak_2": None,
                    "peak": None
                }

            # Process statistics for tomorrow if available
            tomorrow_stats = {
                "min": None,
                "max": None,
                "average": None,
                "off_peak_1": None,
                "off_peak_2": None,
                "peak": None
            }

            tomorrow_prices = self.adapter.get_tomorrow_prices()
            if tomorrow_prices:
                tomorrow_stats = {
                    "min": min(tomorrow_prices) if tomorrow_prices else None,
                    "max": max(tomorrow_prices) if tomorrow_prices else None,
                    "average": sum(tomorrow_prices) / len(tomorrow_prices) if tomorrow_prices else None,
                    "off_peak_1": None,  # These would be calculated properly in a real implementation
                    "off_peak_2": None,
                    "peak": None
                }

            # Build fallback information
            primary_source = self.api.__class__.__name__ if self.api else None
            fallback_info = {
                "primary_source": primary_source,
                "active_source": self._active_source,
                "fallback_used": self._fallback_used,
                "attempted_sources": self._attempted_sources
            }

            # Calculate next update time
            next_update = dt_util.now() + self.update_interval

            # Extract essential raw values
            raw_values = {}
            if "raw_values" in today_data:
                raw_values["today"] = today_data["raw_values"]
            if tomorrow_data and "raw_values" in tomorrow_data:
                raw_values["tomorrow"] = tomorrow_data["raw_values"]

            # Return data that will be passed to sensors - without large raw data
            result = {
                "adapter": self.adapter,
                ATTR_CURRENT_PRICE: self.adapter.get_current_price(),
                ATTR_TODAY: self.adapter.get_today_prices(),
                ATTR_TOMORROW: self.adapter.get_tomorrow_prices(),
                ATTR_RAW_TODAY: self.adapter.get_raw_prices_for_day(0),
                ATTR_RAW_TOMORROW: self.adapter.get_raw_prices_for_day(1),
                "today_stats": today_stats,
                "tomorrow_stats": tomorrow_stats,
                ATTR_TOMORROW_VALID: self.adapter.is_tomorrow_valid(),
                ATTR_LAST_UPDATED: dt_util.now().isoformat(),
                "next_update": next_update.isoformat(),
                ATTR_DATA_SOURCE: self._active_source,
                ATTR_FALLBACK_USED: self._fallback_used,
                "raw_values": raw_values,
                "fallback_info": fallback_info
            }

            _LOGGER.info(f"Successfully updated data with current price: {result[ATTR_CURRENT_PRICE]}")
            self._last_successful_data = result
            return result

        except Exception as err:
            _LOGGER.error(f"Error fetching electricity price data: {err}")
            if self._last_successful_data:
                _LOGGER.warning("Using cached data from last successful update")
                return self._last_successful_data
            raise
