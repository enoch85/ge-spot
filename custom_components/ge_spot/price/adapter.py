"""Price data adapter for electricity spot prices."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..const.sources import Source
from ..timezone.timezone_utils import get_source_timezone

_LOGGER = logging.getLogger(__name__)

class ElectricityPriceAdapter:
    """Adapter for electricity price data with simplified API."""

    def __init__(self, hass: HomeAssistant, raw_data: List[Dict], source_type: str, use_subunit: bool = False) -> None:
        """Initialize the price adapter."""
        self.hass = hass
        self.raw_data = raw_data or []
        self.use_subunit = use_subunit

        # Get today's and tomorrow's dates for reference only
        self.today = datetime.now(timezone.utc).date()
        self.tomorrow = self.today + timedelta(days=1)

        # Store source type
        self.source_type = source_type
        
        # Extract all hourly prices with their ISO timestamps
        from ..utils.price_extractor import extract_all_hourly_prices, extract_adapter_tomorrow_prices
        self.all_hourly_prices = extract_all_hourly_prices(self.raw_data)
        
        # Get source timezone from source type using the constants
        source_timezone = get_source_timezone(self.source_type)
        
        # Use the timezone service to sort prices into today and tomorrow
        # based on actual dates
        from ..timezone import TimezoneService
        tz_service = TimezoneService(self.hass)
        today_prices, tomorrow_prices = tz_service.sort_today_tomorrow(
            self.all_hourly_prices,
            source_timezone=source_timezone
        )
        
        # Store the sorted prices
        self.today_prices = today_prices
        self.tomorrow_prices = tomorrow_prices
        
        # Extract tomorrow dates for validation
        _, self.tomorrow_dates_by_hour = extract_adapter_tomorrow_prices(self.raw_data)
        
        # Convert to price lists
        self.price_list = self._convert_to_price_list(self.today_prices)
        self.tomorrow_list = self._convert_to_price_list(self.tomorrow_prices)

    # These methods have been moved to utils/price_extractor.py

    def _convert_to_price_list(self, price_dict: Dict[str, float]) -> List[float]:
        """Convert price dictionary to ordered list."""
        price_list = []

        # Format as sorted hour keys to ensure proper ordering
        for hour in range(24):
            hour_key = f"{hour:02d}:00"
            if hour_key in price_dict:
                price_list.append(price_dict[hour_key])

        return price_list

    def get_current_price(self, area=None, config=None) -> Optional[float]:
        """Get price for the current hour."""
        # Use TimezoneService for consistent current hour calculation
        if hasattr(self, 'hass') and self.hass:
            from ..timezone import TimezoneService
            # Pass area and config to TimezoneService
            tz_service = TimezoneService(self.hass, area, config)
            hour_str = tz_service.get_current_hour_key()
            _LOGGER.debug(f"Using TimezoneService for area {area} to get current hour: {hour_str}")
        else:
            now = dt_util.now()
            hour_str = f"{now.hour:02d}:00"
            _LOGGER.debug(f"No TimezoneService available, using system time for current hour: {hour_str}")

        # Check if we have any data at all
        if not self.today_prices:
            _LOGGER.warning(f"No today prices available for current hour {hour_str}")
            return None

        # Look for the current hour in today's data
        if hour_str in self.today_prices:
            price = self.today_prices[hour_str]
            _LOGGER.debug(f"Found current price for hour {hour_str}: {price}")
            return price
            
        # If key not found, log error with available hours for debugging
        available_hours = sorted(list(self.today_prices.keys()))
        _LOGGER.error(f"Current hour key '{hour_str}' not found in available hours: {available_hours}")
        return None

    def find_next_price(self, area=None, config=None) -> Optional[float]:
        """Get price for the next hour."""
        # Use TimezoneService for consistent hour calculation
        if hasattr(self, 'hass') and self.hass:
            from ..timezone import TimezoneService
            # Pass area and config to TimezoneService
            tz_service = TimezoneService(self.hass, area, config)
            current_hour_key = tz_service.get_current_hour_key()
            hour = int(current_hour_key.split(':')[0])
            next_hour = (hour + 1) % 24
            _LOGGER.debug(f"Using TimezoneService for area {area} to get next hour: current hour {current_hour_key} -> next hour {next_hour:02d}:00")
        else:
            now = dt_util.now()
            next_hour = (now.hour + 1) % 24
            _LOGGER.debug(f"No TimezoneService available, using system time for next hour: {next_hour:02d}:00")

        hour_str = f"{next_hour:02d}:00"
        
        # Check if we have any data at all
        if not self.today_prices and not self.tomorrow_prices:
            _LOGGER.warning(f"No hourly prices available for next hour {hour_str}")
            return None
            
        # First check today's data
        if hour_str in self.today_prices:
            price = self.today_prices[hour_str]
            _LOGGER.debug(f"Found next price for hour {hour_str} in today's data")
            return price
            
        # If not found in today's data, check tomorrow's data
        # This is valid for next_hour since it might legitimately be in tomorrow if we're near midnight
        if hour_str in self.tomorrow_prices:
            price = self.tomorrow_prices[hour_str]
            _LOGGER.debug(f"Found next price for hour {hour_str} in tomorrow's data (likely near midnight)")
            return price

        # If key not found, log error with available hours for debugging
        today_hours = sorted(list(self.today_prices.keys())) if self.today_prices else []
        tomorrow_hours = sorted(list(self.tomorrow_prices.keys())) if self.tomorrow_prices else []
        _LOGGER.error(f"Next hour key '{hour_str}' not found in any available hours. Today: {today_hours}, Tomorrow: {tomorrow_hours}")
        return None

    def get_today_prices(self) -> List[float]:
        """Get list of today's prices in order."""
        return self.price_list

    def get_tomorrow_prices(self) -> List[float]:
        """Get list of tomorrow's prices in order."""
        return self.tomorrow_list

    def get_prices_with_timestamps(self, day_offset: int = 0) -> Dict[str, float]:
        """Get dictionary of ISO timestamp -> price."""
        # Get appropriate price dictionary
        prices = self.tomorrow_prices if day_offset == 1 else self.today_prices

        # Get base date
        base_date = dt_util.now().date()
        if day_offset == 1:
            base_date = base_date + timedelta(days=1)

        # Create timestamp -> price dictionary
        result = {}
        for hour in range(24):
            hour_key = f"{hour:02d}:00"
            if hour_key in prices:
                # Create ISO timestamp for this hour
                dt = datetime.combine(base_date, datetime.min.time().replace(hour=hour))
                timestamp = dt.isoformat()
                result[timestamp] = prices[hour_key]

        return result

    def get_day_statistics(self, day_offset: int = 0) -> Dict[str, Any]:
        """Calculate statistics for a day."""
        # Use appropriate price list based on day offset
        price_list = self.tomorrow_list if day_offset == 1 else self.price_list

        if not price_list:
            return {
                "min": None,
                "max": None,
                "average": None,
                "min_timestamp": None,
                "max_timestamp": None,
            }

        # Basic statistics
        min_price = min(price_list) if price_list else None
        max_price = max(price_list) if price_list else None
        avg_price = sum(price_list) / len(price_list) if price_list else None

        # Find timestamps for min/max
        min_hour = price_list.index(min_price) if min_price is not None else None
        max_hour = price_list.index(max_price) if max_price is not None else None

        # Create ISO timestamp strings
        base_date = dt_util.now().date()
        if day_offset == 1:
            base_date = base_date + timedelta(days=1)

        min_timestamp = None
        if min_hour is not None:
            min_dt = datetime.combine(base_date, datetime.min.time().replace(hour=min_hour))
            min_timestamp = min_dt.isoformat()

        max_timestamp = None
        if max_hour is not None:
            max_dt = datetime.combine(base_date, datetime.min.time().replace(hour=max_hour))
            max_timestamp = max_dt.isoformat()

        return {
            "min": min_price,
            "max": max_price,
            "average": avg_price,
            "min_timestamp": min_timestamp,
            "max_timestamp": max_timestamp,
        }

    def is_tomorrow_valid(self) -> bool:
        """Check if tomorrow's data is available and valid."""
        # Check if we have any tomorrow data at all
        if not self.tomorrow_list:
            _LOGGER.debug("No tomorrow data available")
            return False

        # Consider valid if we have at least 12 hours of data (half a day)
        # This is more flexible than the previous 20 hour requirement
        is_valid = len(self.tomorrow_list) >= 12

        # Log detailed validation information
        _LOGGER.debug(f"Tomorrow data validation: {len(self.tomorrow_list)}/24 hours available, valid: {is_valid}")

        # For hours between 12 and 20, log with higher visibility as this is a "partial" valid state
        if 12 <= len(self.tomorrow_list) < 20:
            _LOGGER.info(f"Partial tomorrow data available: {len(self.tomorrow_list)}/24 hours - treating as valid")

        # Check if we have date information for tomorrow's data
        if is_valid and self.tomorrow_dates_by_hour:
            # We have date information, so we can verify that the data is actually for tomorrow
            tomorrow_date = datetime.now(timezone.utc).date() + timedelta(days=1)
            
            # Check if at least one date matches tomorrow
            has_tomorrow_date = False
            for hour_key, dt in self.tomorrow_dates_by_hour.items():
                if dt.date() == tomorrow_date:
                    has_tomorrow_date = True
                    break
            
            if not has_tomorrow_date:
                _LOGGER.warning(f"Tomorrow's data does not contain any entries for tomorrow's date ({tomorrow_date})")
                is_valid = False
            else:
                _LOGGER.debug(f"Tomorrow's data contains entries for tomorrow's date ({tomorrow_date})")

        return is_valid
