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
        
        # Transform raw data format if necessary
        self.processed_raw_data = []
        for item in self.raw_data:
            # Skip non-dictionary items
            if not isinstance(item, dict):
                continue
                
            # Find price data which may be in different formats from different APIs
            if all(key in item for key in ["start", "end", "value"]):
                # Already in the correct format
                self.processed_raw_data.append(item)
            elif "current_price" in item and "hourly_prices" in item:
                # Process hourly prices into individual periods
                for hour_str, price in item.get("hourly_prices", {}).items():
                    try:
                        # Parse hour string (format: "HH:00")
                        hour = int(hour_str.split(":")[0])
                        
                        # Create a start and end time for this hour
                        now = dt_util.now()
                        start_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                        end_time = start_time.replace(hour=hour+1) if hour < 23 else start_time.replace(hour=0, day=start_time.day+1)
                        
                        self.processed_raw_data.append({
                            "start": start_time.isoformat(),
                            "end": end_time.isoformat(),
                            "value": price
                        })
                    except (ValueError, IndexError) as e:
                        _LOGGER.warning(f"Error processing hourly price {hour_str}: {e}")
                        
        # Process data into periods
        self.price_periods = process_price_data(self.processed_raw_data, self.local_tz)
    
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
