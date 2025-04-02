"""Price data adapter for electricity spot prices."""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .utils.timezone_utils import (
    process_price_data,
    find_current_price,
    get_prices_for_day,
    get_raw_prices_for_day,
    get_price_list,
    get_statistics,
    is_tomorrow_valid,
)

_LOGGER = logging.getLogger(__name__)

class ElectricityPriceAdapter:
    """A robust adapter for electricity price data with proper timezone handling."""

    def __init__(self, hass: HomeAssistant, raw_data: List[Dict]) -> None:
        """Initialize the price adapter."""
        self.hass = hass
        self.raw_data = raw_data or []
        self.local_tz = dt_util.get_time_zone(hass.config.time_zone)
        self.price_periods = self._process_price_data()
    
    def _process_price_data(self) -> List[Dict]:
        """Process raw data into clean, timezone-aware period objects."""
        return process_price_data(self.raw_data, self.local_tz)
    
    def get_current_price(self, reference_time: Optional[datetime] = None) -> Optional[float]:
        """Get price for the current period."""
        return find_current_price(self.price_periods, reference_time)
    
    def get_prices_for_day(self, day_offset: int = 0) -> List[Dict]:
        """Get all prices for a specific day (today + offset)."""
        return get_prices_for_day(self.price_periods, day_offset)
    
    def get_raw_prices_for_day(self, day_offset: int = 0) -> List[Dict]:
        """Get raw price data formatted for Home Assistant attributes."""
        day_data = self.get_prices_for_day(day_offset)
        return get_raw_prices_for_day(day_data)
    
    def get_today_prices(self) -> List[float]:
        """Get list of today's prices in chronological order."""
        return get_price_list(self.get_prices_for_day(0))
    
    def get_tomorrow_prices(self) -> List[float]:
        """Get list of tomorrow's prices in chronological order."""
        return get_price_list(self.get_prices_for_day(1))
    
    def get_day_statistics(self, day_offset: int = 0) -> Dict[str, Any]:
        """Calculate statistics for a particular day."""
        return get_statistics(self.get_prices_for_day(day_offset))
    
    def is_tomorrow_valid(self) -> bool:
        """Check if tomorrow's data is available."""
        return is_tomorrow_valid(self.price_periods)
