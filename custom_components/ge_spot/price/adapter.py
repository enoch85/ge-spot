"""Price data adapter for electricity spot prices."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

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

        # Get today's and tomorrow's dates for comparison
        self.today = datetime.now(timezone.utc).date()
        self.tomorrow = self.today + timedelta(days=1)

        # Extract core data once for reuse
        self.today_hourly_prices, self.dates_by_hour = self._extract_hourly_prices()
        self.tomorrow_prices, self.tomorrow_dates_by_hour = self._extract_tomorrow_prices()

        # If we don't have tomorrow prices but have dates in today_hourly_prices,
        # try to extract tomorrow data with dates
        if not self.tomorrow_prices and self.dates_by_hour:
            self._extract_tomorrow_from_today()

        self.price_list = self._convert_to_price_list(self.today_hourly_prices)
        self.tomorrow_list = self._convert_to_price_list(self.tomorrow_prices)

    def _parse_hour_from_string(self, hour_str: str) -> Tuple[Optional[int], Optional[datetime]]:
        """Parse hour and date from hour string.

        Args:
            hour_str: Hour string in either "HH:00", "tomorrow_HH:00", or ISO format

        Returns:
            Tuple of (hour, datetime) where hour is an integer 0-23 and datetime is the full datetime
            if available, or None if not available
        """
        try:
            # Check if this is a tomorrow hour from timezone conversion
            if hour_str.startswith("tomorrow_"):
                # Extract the hour key without the prefix
                hour_key = hour_str[9:]  # Remove "tomorrow_" prefix
                try:
                    hour = int(hour_key.split(":")[0])
                    if 0 <= hour < 24:  # Only accept valid hours
                        # Create a datetime for tomorrow with this hour
                        dt = datetime.combine(self.tomorrow, datetime.min.time().replace(hour=hour), timezone.utc)
                        return hour, dt
                except (ValueError, IndexError):
                    pass

            # Try simple "HH:00" format
            try:
                hour = int(hour_str.split(":")[0])
                if 0 <= hour < 24:
                    return hour, None
            except (ValueError, IndexError):
                pass

            # Try ISO format
            if "T" in hour_str:
                # Handle ISO format with timezone
                dt = datetime.fromisoformat(hour_str.replace('Z', '+00:00'))
                return dt.hour, dt
        except Exception as e:
            _LOGGER.debug(f"Error parsing hour string '{hour_str}': {e}")

        # If we get here, we couldn't parse the hour
        _LOGGER.debug(f"Could not parse hour from: {hour_str}")
        return None, None

    def _extract_hourly_prices(self) -> Tuple[Dict[str, float], Dict[str, datetime]]:
        """Extract hourly prices from raw data and separate tomorrow's data.

        Returns:
            Tuple of (hourly_prices, dates_by_hour) where hourly_prices is a dict of hour_key -> price
            and dates_by_hour is a dict of hour_key -> datetime
        """
        hourly_prices = {}
        dates_by_hour = {}
        tomorrow_in_today = {}  # Temporary dict to collect tomorrow's data found in today_hourly_prices

        for item in self.raw_data:
            if not isinstance(item, dict):
                continue

            # Only process the new format
            if "today_hourly_prices" in item and isinstance(item["today_hourly_prices"], dict):
                # Store formatted hour -> price mapping
                _LOGGER.debug(f"Found today_hourly_prices in raw data: {len(item['today_hourly_prices'])} entries")

                for hour_str, price in item["today_hourly_prices"].items():
                    hour, dt = self._parse_hour_from_string(hour_str)

                    if hour is not None:
                        hour_key = f"{hour:02d}:00"
                        hourly_prices[hour_key] = price
                        if dt is not None:
                            dates_by_hour[hour_key] = dt

        _LOGGER.debug(f"Extracted {len(hourly_prices)} hourly prices: {sorted(hourly_prices.keys())}")

        # If we found tomorrow's data, store it for later extraction
        if tomorrow_in_today:
            _LOGGER.info(f"Found {len(tomorrow_in_today)} hours of tomorrow's data in today_hourly_prices")
            self._tomorrow_in_today = tomorrow_in_today

        return hourly_prices, dates_by_hour

    def _extract_tomorrow_prices(self) -> Tuple[Dict[str, float], Dict[str, datetime]]:
        """Extract tomorrow's hourly prices from raw data.

        Returns:
            Tuple of (tomorrow_prices, tomorrow_dates_by_hour) where tomorrow_prices is a dict of hour_key -> price
            and tomorrow_dates_by_hour is a dict of hour_key -> datetime
        """
        tomorrow_prices = {}
        tomorrow_dates_by_hour = {}

        for item in self.raw_data:
            if not isinstance(item, dict):
                continue

            # First try the prefixed format which is guaranteed to be recognized
            if "tomorrow_prefixed_prices" in item and isinstance(item["tomorrow_prefixed_prices"], dict):
                # Store formatted hour -> price mapping
                _LOGGER.debug(f"Found tomorrow_prefixed_prices in raw data: {len(item['tomorrow_prefixed_prices'])} entries")
                for hour_str, price in item["tomorrow_prefixed_prices"].items():
                    if hour_str.startswith("tomorrow_"):
                        # Extract the hour key without the prefix
                        hour_key = hour_str[9:]  # Remove "tomorrow_" prefix
                        # We can use this directly
                        tomorrow_prices[hour_key] = price

                        # Create a datetime for tomorrow with this hour
                        try:
                            hour = int(hour_key.split(":")[0])
                            dt = datetime.combine(self.tomorrow, datetime.min.time().replace(hour=hour), timezone.utc)
                            tomorrow_dates_by_hour[hour_key] = dt
                        except (ValueError, IndexError):
                            pass

                        _LOGGER.debug(f"Added prefixed tomorrow price: {hour_key} -> {price}")

            # Then try the standard tomorrow_hourly_prices
            elif "tomorrow_hourly_prices" in item and isinstance(item["tomorrow_hourly_prices"], dict):
                # Store formatted hour -> price mapping
                _LOGGER.debug(f"Found tomorrow_hourly_prices in raw data: {len(item['tomorrow_hourly_prices'])} entries")
                for hour_str, price in item["tomorrow_hourly_prices"].items():
                    hour, dt = self._parse_hour_from_string(hour_str)
                    if hour is not None:
                        hour_key = f"{hour:02d}:00"
                        tomorrow_prices[hour_key] = price
                        if dt is not None:
                            tomorrow_dates_by_hour[hour_key] = dt
                        _LOGGER.debug(f"Added tomorrow price: {hour_key} -> {price}")

        _LOGGER.debug(f"Extracted {len(tomorrow_prices)} tomorrow prices: {sorted(tomorrow_prices.keys())}")
        return tomorrow_prices, tomorrow_dates_by_hour

    def _extract_tomorrow_from_today(self) -> None:
        """Extract tomorrow's data from today_hourly_prices if dates are available."""
        # First check if we already detected tomorrow's data during today prices extraction
        if hasattr(self, '_tomorrow_in_today') and self._tomorrow_in_today:
            # Move tomorrow data to tomorrow_prices directly
            for hour_key, price in self._tomorrow_in_today.items():
                self.tomorrow_prices[hour_key] = price

                # Create a datetime for tomorrow with this hour
                try:
                    hour = int(hour_key.split(":")[0])
                    dt = datetime.combine(self.tomorrow, datetime.min.time().replace(hour=hour), timezone.utc)
                    self.tomorrow_dates_by_hour[hour_key] = dt
                except (ValueError, IndexError):
                    pass

            _LOGGER.info(f"Used {len(self._tomorrow_in_today)} hours of tomorrow's data found during extraction")
            return

        # Traditional extraction based on dates if no pre-detected tomorrow data
        if not self.dates_by_hour:
            _LOGGER.debug("No dates available for extracting tomorrow's data")
            return

        # Look for hours with tomorrow's date
        tomorrow_hour_keys = []
        for hour_key, dt in self.dates_by_hour.items():
            if dt.date() == self.tomorrow:
                # This is tomorrow's data, move it to tomorrow_prices
                self.tomorrow_prices[hour_key] = self.today_hourly_prices[hour_key]
                self.tomorrow_dates_by_hour[hour_key] = dt
                tomorrow_hour_keys.append(hour_key)

        # Remove tomorrow's data from today_hourly_prices if we found any
        if self.tomorrow_prices:
            _LOGGER.info(f"Extracted {len(self.tomorrow_prices)} hours of tomorrow's data from today_hourly_prices")

            # Remove tomorrow's hours from today_hourly_prices
            for hour_key in tomorrow_hour_keys:
                if hour_key in self.today_hourly_prices:
                    del self.today_hourly_prices[hour_key]

            _LOGGER.info(f"Kept {len(self.today_hourly_prices)} hours of today's data in today_hourly_prices")

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
        if not self.today_hourly_prices:
            _LOGGER.warning(f"No today hourly prices available for current hour {hour_str}")
            return None

        # Look for the current hour in today's data
        if hour_str in self.today_hourly_prices:
            price = self.today_hourly_prices[hour_str]
            _LOGGER.debug(f"Found current price for hour {hour_str}: {price}")
            return price
            
        # If key not found, log error with available hours for debugging
        available_hours = sorted(list(self.today_hourly_prices.keys()))
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
        if not self.today_hourly_prices and not self.tomorrow_prices:
            _LOGGER.warning(f"No hourly prices available for next hour {hour_str}")
            return None
            
        # First check today's data
        if hour_str in self.today_hourly_prices:
            price = self.today_hourly_prices[hour_str]
            _LOGGER.debug(f"Found next price for hour {hour_str} in today's data")
            return price
            
        # If not found in today's data, check tomorrow's data
        # This is valid for next_hour since it might legitimately be in tomorrow if we're near midnight
        if hour_str in self.tomorrow_prices:
            price = self.tomorrow_prices[hour_str]
            _LOGGER.debug(f"Found next price for hour {hour_str} in tomorrow's data (likely near midnight)")
            return price

        # If key not found, log error with available hours for debugging
        today_hours = sorted(list(self.today_hourly_prices.keys())) if self.today_hourly_prices else []
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
        prices = self.tomorrow_prices if day_offset == 1 else self.today_hourly_prices

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
