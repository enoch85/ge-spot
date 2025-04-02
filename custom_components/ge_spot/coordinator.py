"""Data update coordinator for electricity spot prices."""
import logging
from datetime import timedelta
from typing import Any, Dict, Optional
import datetime

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .price_adapter import ElectricityPriceAdapter
from .const import (
    ATTR_CURRENT_PRICE,
    ATTR_TODAY,
    ATTR_TOMORROW,
    ATTR_RAW_TODAY,
    ATTR_RAW_TOMORROW,
    ATTR_TOMORROW_VALID,
    ATTR_LAST_UPDATED,
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
    
    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            _LOGGER.debug(f"Updating data for area {self.area} with currency {self.currency}")
            # Fetch today's data
            today_data = await self.api.fetch_day_ahead_prices(
                self.area, 
                self.currency,
                dt_util.now()
            )
            
            if not today_data:
                _LOGGER.error("Failed to fetch today's price data")
                if self._last_successful_data:
                    _LOGGER.warning("Using cached data from last successful update")
                    return self._last_successful_data
                return None
            
            # Try to fetch tomorrow's data if after 1 PM
            tomorrow_data = None
            now = dt_util.as_local(dt_util.now())
            if now.hour >= 13:
                try:
                    tomorrow_data = await self.api.fetch_day_ahead_prices(
                        self.area,
                        self.currency,
                        dt_util.now() + timedelta(days=1)
                    )
                    if tomorrow_data:
                        _LOGGER.debug("Successfully fetched tomorrow's price data")
                    else:
                        _LOGGER.warning("Tomorrow's price data is empty or not available")
                except Exception as err:
                    _LOGGER.warning(f"Failed to fetch tomorrow's prices: {err}")
            else:
                _LOGGER.debug(f"Not fetching tomorrow's data yet, current hour: {now.hour}")
            
            # Combine the data
            all_data = []
            if today_data:
                all_data.append(today_data)
            if tomorrow_data:
                all_data.append(tomorrow_data)
                
            # Create adapter with processed data
            _LOGGER.debug("Creating price adapter with fetched data")
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
            
            # Return data that will be passed to sensors
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
            }
            
            _LOGGER.debug(f"Successfully updated data with current price: {result[ATTR_CURRENT_PRICE]}")
            self._last_successful_data = result
            return result
            
        except Exception as err:
            _LOGGER.error(f"Error fetching electricity price data: {err}")
            if self._last_successful_data:
                _LOGGER.warning("Using cached data from last successful update")
                return self._last_successful_data
            raise
