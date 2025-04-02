"""Data update coordinator for electricity spot prices."""
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

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
    
    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            # Fetch today's data
            today_data = await self.api.fetch_day_ahead_prices(
                self.area, 
                self.currency,
                dt_util.now()
            )
            
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
                except Exception as err:
                    _LOGGER.warning("Failed to fetch tomorrow's prices: %s", err)
            
            # Combine the data
            all_data = []
            if today_data:
                all_data.extend(today_data)
            if tomorrow_data:
                all_data.extend(tomorrow_data)
                
            # Create adapter with processed data
            self.adapter = ElectricityPriceAdapter(self.hass, all_data)
            
            # Return data that will be passed to sensors
            return {
                "adapter": self.adapter,
                ATTR_CURRENT_PRICE: self.adapter.get_current_price(),
                ATTR_TODAY: self.adapter.get_today_prices(),
                ATTR_TOMORROW: self.adapter.get_tomorrow_prices(),
                ATTR_RAW_TODAY: self.adapter.get_raw_prices_for_day(0),
                ATTR_RAW_TOMORROW: self.adapter.get_raw_prices_for_day(1),
                "today_stats": self.adapter.get_day_statistics(0),
                "tomorrow_stats": self.adapter.get_day_statistics(1),
                ATTR_TOMORROW_VALID: self.adapter.is_tomorrow_valid(),
                ATTR_LAST_UPDATED: dt_util.now().isoformat(),
            }
        except Exception as err:
            _LOGGER.error("Error fetching electricity price data: %s", err)
            raise
