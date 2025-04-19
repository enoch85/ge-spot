"""Price data adapter for electricity spot prices."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

class ElectricityPriceAdapter:
    """Adapter for electricity price data with simplified API."""

    def __init__(self, hass: HomeAssistant, raw_data: List[Dict], use_subunit: bool = False) -> None:
        """Initialize the price adapter."""
        self.hass = hass
        self.raw_data = raw_data or []
        self.use_subunit = use_subunit

        # Extract core data once for reuse
        self.hourly_prices = self._extract_hourly_prices()
        self.tomorrow_prices = self._extract_tomorrow_prices()
        self.price_list = self._convert_to_price_list(self.hourly_prices)
        self.tomorrow_list = self._convert_to_price_list(self.tomorrow_prices)

    def _extract_hourly_prices(self) -> Dict[str, float]:
        """Extract hourly prices from raw data."""
        hourly_prices = {}

        for item in self.raw_data:
            if not isinstance(item, dict):
                continue

            if "hourly_prices" in item and isinstance(item["hourly_prices"], dict):
                # Store formatted hour -> price mapping
                _LOGGER.debug(f"Found hourly_prices in raw data: {len(item['hourly_prices'])} entries")
                for hour_str, price in item["hourly_prices"].items():
                    try:
                        hour = int(hour_str.split(":")[0])
                        if 0 <= hour < 24:  # Only accept valid hours
                            hourly_prices[f"{hour:02d}:00"] = price
                    except (ValueError, IndexError):
                        _LOGGER.warning(f"Invalid hour format in hourly_prices: {hour_str}")

        _LOGGER.debug(f"Extracted {len(hourly_prices)} hourly prices: {sorted(hourly_prices.keys())}")
        return hourly_prices

    def _extract_tomorrow_prices(self) -> Dict[str, float]:
        """Extract tomorrow's hourly prices from raw data."""
        tomorrow_prices = {}

        for item in self.raw_data:
            if not isinstance(item, dict):
                continue

            if "tomorrow_hourly_prices" in item and isinstance(item["tomorrow_hourly_prices"], dict):
                # Store formatted hour -> price mapping
                _LOGGER.debug(f"Found tomorrow_hourly_prices in raw data: {len(item['tomorrow_hourly_prices'])} entries")
                for hour_str, price in item["tomorrow_hourly_prices"].items():
                    try:
                        hour = int(hour_str.split(":")[0])
                        if 0 <= hour < 24:  # Only accept valid hours
                            tomorrow_prices[f"{hour:02d}:00"] = price
                    except (ValueError, IndexError):
                        _LOGGER.warning(f"Invalid hour format in tomorrow_hourly_prices: {hour_str}")

        _LOGGER.debug(f"Extracted {len(tomorrow_prices)} tomorrow prices: {sorted(tomorrow_prices.keys())}")
        return tomorrow_prices

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
            _LOGGER.debug(f"TimezoneService details - HA timezone: {tz_service.ha_timezone}, Area timezone: {tz_service.area_timezone}, Reference: {tz_service.timezone_reference}")
        else:
            now = dt_util.now()
            hour_str = f"{now.hour:02d}:00"
            _LOGGER.debug(f"No TimezoneService available, using system time for current hour: {hour_str}")

        _LOGGER.debug(f"Looking for current price at hour {hour_str}, available hours: {sorted(list(self.hourly_prices.keys()))}")

        if hour_str in self.hourly_prices:
            price = self.hourly_prices[hour_str]
            _LOGGER.debug(f"Found current price for hour {hour_str}: {price}")
            return price

        # If key not found, log error and return None
        _LOGGER.error(f"Current hour key '{hour_str}' not found in available hours: {sorted(list(self.hourly_prices.keys()))}")
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
        _LOGGER.debug(f"Looking for next price at hour {hour_str}, available hours: {sorted(list(self.hourly_prices.keys()))}")

        if hour_str in self.hourly_prices:
            price = self.hourly_prices[hour_str]
            _LOGGER.debug(f"Found next price for hour {hour_str}: {price}")
            return price

        # If key not found, log error and return None
        _LOGGER.error(f"Next hour key '{hour_str}' not found in available hours: {sorted(list(self.hourly_prices.keys()))}")
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
        prices = self.tomorrow_prices if day_offset == 1 else self.hourly_prices

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
        """Check if tomorrow's data is available."""
        # Consider valid if we have at least 20 hours of data
        is_valid = len(self.tomorrow_list) >= 20
        _LOGGER.debug(f"Tomorrow data validation: {len(self.tomorrow_list)}/24 hours available, valid: {is_valid}")
        return is_valid
