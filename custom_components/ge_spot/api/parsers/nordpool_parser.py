"""Parser for Nordpool API responses."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple

from ...const.sources import Source
from ...timezone.timezone_utils import normalize_hour_value
from ...utils.validation import validate_data
from ..base.price_parser import BasePriceParser

_LOGGER = logging.getLogger(__name__)

class NordpoolPriceParser(BasePriceParser):
    """Parser for Nordpool API responses."""

    def __init__(self, timezone_service=None):
        """Initialize the parser."""
        super().__init__(Source.NORDPOOL, timezone_service)
        _LOGGER.debug("Initialized Nordpool parser with standardized timestamp handling")

    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Nordpool API response.

        Args:
            data: Raw API response data

        Returns:
            Parsed data with hourly prices
        """
        # Validate data
        data = validate_data(data, self.source)

        result = {
            "today_hourly_prices": {},
            "currency": data.get("currency", "EUR"),
            "source": self.source
        }

        # Extract hourly prices
        if "data" in data and "Areas" in data["data"]:
            areas = data["data"]["Areas"]

            # Find the first area with prices
            for area_code, area_data in areas.items():
                if "values" in area_data:
                    values = area_data["values"]

                    for value in values:
                        if "start" in value and "end" in value and "value" in value:
                            start_time = self._parse_timestamp(value["start"])
                            price = self._parse_price(value["value"])

                            if start_time and price is not None:
                                # Format as ISO string for the hour
                                hour_key = start_time.strftime("%Y-%m-%dT%H:00:00")
                                result["today_hourly_prices"][hour_key] = price

                    # Only process the first area with prices
                    if result["today_hourly_prices"]:
                        break

        # If hourly prices were already processed
        if "hourly_prices" in data and isinstance(data["hourly_prices"], dict):
            result["today_hourly_prices"] = data["hourly_prices"]
        # Support for new format if it exists
        elif "today_hourly_prices" in data and isinstance(data["today_hourly_prices"], dict):
            result["today_hourly_prices"] = data["today_hourly_prices"]

        # Add current and next hour prices if available
        if "current_price" in data:
            result["current_price"] = data["current_price"]

        if "next_hour_price" in data:
            result["next_hour_price"] = data["next_hour_price"]

        # Calculate current and next hour prices if not provided
        if "current_price" not in result:
            result["current_price"] = self._get_current_price(result["today_hourly_prices"])

        if "next_hour_price" not in result:
            result["next_hour_price"] = self._get_next_hour_price(result["today_hourly_prices"])

        # Calculate day average if enough prices
        if len(result["today_hourly_prices"]) >= 12:
            result["day_average_price"] = self._calculate_day_average(result["today_hourly_prices"])

        return result

    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse timestamp from Nordpool format.

        Args:
            timestamp_str: Timestamp string

        Returns:
            Parsed datetime or None if parsing fails
        """
        # Use the standard timestamp parser from BasePriceParser
        dt = super().parse_timestamp(timestamp_str)
        
        if dt is not None:
            return dt
            
        # If standard parser failed, try Nordpool specific format
        try:
            # Try Nordpool specific format with milliseconds
            dt = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%f")
            # Ensure it's timezone-aware
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            _LOGGER.debug(f"Parsed Nordpool specific timestamp format: {timestamp_str} -> {dt}")
            return dt
        except (ValueError, AttributeError):
            _LOGGER.debug(f"Failed to parse Nordpool timestamp with all methods: {timestamp_str}")
            return None

    def _parse_price(self, price_value: Any) -> Optional[float]:
        """Parse price value.

        Args:
            price_value: Price value from API

        Returns:
            Parsed price or None if parsing fails
        """
        try:
            price = float(price_value)
            return price
        except (ValueError, TypeError):
            _LOGGER.warning(f"Failed to parse price: {price_value}")
            return None

    def _get_current_price(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Get current hour price.

        Args:
            hourly_prices: Dictionary of hourly prices

        Returns:
            Current hour price or None if not available
        """
        if not hourly_prices:
            return None

        now = datetime.now(timezone.utc)
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        current_hour_key = current_hour.strftime("%Y-%m-%dT%H:00:00")

        # First try exact ISO format key match
        if current_hour_key in hourly_prices:
            return hourly_prices[current_hour_key]
        
        # Try alternative format (HH:00)
        simple_key = f"{current_hour.hour:02d}:00"
        if simple_key in hourly_prices:
            return hourly_prices[simple_key]
            
        # If neither found, look for any matching hour regardless of date
        for key, price in hourly_prices.items():
            if "T" in key:  # Check for ISO format key, matching ENTSO-E approach
                try:
                    dt = datetime.fromisoformat(key.replace('Z', '+00:00'))
                    if dt.hour == current_hour.hour:
                        return price
                except (ValueError, TypeError):
                    continue
                    
        return None

    def _get_next_hour_price(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Get next hour price.

        Args:
            hourly_prices: Dictionary of hourly prices

        Returns:
            Next hour price or None if not available
        """
        if not hourly_prices:
            return None

        now = datetime.now(timezone.utc)
        next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
        next_hour_key = next_hour.strftime("%Y-%m-%dT%H:00:00")

        # First try exact ISO format key match
        if next_hour_key in hourly_prices:
            return hourly_prices[next_hour_key]
        
        # Try alternative format (HH:00)
        simple_key = f"{next_hour.hour:02d}:00"
        if simple_key in hourly_prices:
            return hourly_prices[simple_key]
            
        # If neither found, look for any matching hour regardless of date
        for key, price in hourly_prices.items():
            if "T" in key:  # Check for ISO format key, matching ENTSO-E approach
                try:
                    dt = datetime.fromisoformat(key.replace('Z', '+00:00'))
                    if dt.hour == next_hour.hour:
                        return price
                except (ValueError, TypeError):
                    continue
                    
        return None

    def _calculate_day_average(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Calculate day average price.

        Args:
            hourly_prices: Dictionary of hourly prices

        Returns:
            Day average price or None if not enough data
        """
        if not hourly_prices:
            return None

        # Get today's date
        today = datetime.now(timezone.utc).date()

        # Filter prices for today
        today_prices = []
        for hour_key, price in hourly_prices.items():
            try:
                if "T" in hour_key:  # Check for ISO format key, matching ENTSO-E approach
                    hour_dt = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
                    if hour_dt.date() == today:
                        today_prices.append(price)
            except (ValueError, TypeError):
                continue

        # Calculate average if we have enough prices
        if len(today_prices) >= 12:
            return sum(today_prices) / len(today_prices)

        return None

    def parse_hourly_prices(self, data: Dict[str, Any], area: str) -> Dict[str, float]:
        """Parse hourly prices from Nordpool data.

        Args:
            data: Raw API response data
            area: Area code

        Returns:
            Dictionary of hourly prices with ISO format timestamp keys or
            a dictionary with both 'today_hourly_prices' and 'tomorrow_hourly_prices'
        """
        today_hourly_prices = {}
        tomorrow_hourly_prices = {}
        
        # Similar approach to ENTSOE - handle the data directly
        if "data" in data and isinstance(data["data"], dict):
            # Process the data using the provided structure
            api_data = data["data"]
            
            # Check if we have multiAreaEntries in the response
            if "multiAreaEntries" in api_data:
                entries = api_data.get("multiAreaEntries", [])
                _LOGGER.debug(f"Processing {len(entries)} entries from multiAreaEntries")
                
                # Process each entry to extract prices
                for entry in entries:
                    if not isinstance(entry, dict) or "entryPerArea" not in entry:
                        continue

                    if area not in entry["entryPerArea"]:
                        continue

                    # Extract values
                    start_time = entry.get("deliveryStart")
                    raw_price = entry["entryPerArea"][area]

                    if start_time and raw_price is not None:
                        # Parse timestamp
                        dt = self._parse_timestamp(start_time)
                        if dt:
                            # Always format as ISO format with full date and time
                            hour_key = super().format_timestamp_to_iso(dt)
                            price_val = float(raw_price)
                            
                            # Check if this timestamp belongs to tomorrow
                            tomorrow_date = self.tomorrow
                            
                            # First determine if it's tomorrow by date comparison
                            is_tomorrow = dt.date() == tomorrow_date
                            
                            # Fallback: try to identify by start_time string pattern
                            if not is_tomorrow and start_time:
                                tomorrow_str = tomorrow_date.strftime("%Y-%m-%d")
                                next_day_str = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
                                
                                if tomorrow_str in start_time or next_day_str in start_time:
                                    is_tomorrow = True
                                    _LOGGER.debug(f"Identified as tomorrow based on string pattern: {start_time}")
                            
                            # Assign to the appropriate dictionary
                            if is_tomorrow:
                                tomorrow_hourly_prices[hour_key] = price_val
                                _LOGGER.debug(f"Added TOMORROW price with ISO timestamp: {hour_key} = {raw_price}")
                            else:
                                today_hourly_prices[hour_key] = price_val
                                _LOGGER.debug(f"Added TODAY price with ISO timestamp: {hour_key} = {raw_price}")
        
        # Alternative: Handle raw multiAreaEntries at top level
        elif "multiAreaEntries" in data:
            entries = data.get("multiAreaEntries", [])
            _LOGGER.debug(f"Processing {len(entries)} entries from top-level multiAreaEntries")

            # Same logic as above, but with top-level entries
            for entry in entries:
                if not isinstance(entry, dict) or "entryPerArea" not in entry:
                    continue

                if area not in entry["entryPerArea"]:
                    continue

                # Extract values
                start_time = entry.get("deliveryStart")
                raw_price = entry["entryPerArea"][area]

                if start_time and raw_price is not None:
                    # Parse timestamp
                    dt = self._parse_timestamp(start_time)
                    if dt:
                        # Always format as ISO format
                        hour_key = super().format_timestamp_to_iso(dt)
                        price_val = float(raw_price)
                        
                        # Check if this timestamp belongs to tomorrow
                        tomorrow_date = self.tomorrow
                        is_tomorrow = dt.date() == tomorrow_date
                        
                        # Fallback check using string pattern
                        if not is_tomorrow and start_time:
                            tomorrow_str = tomorrow_date.strftime("%Y-%m-%d")
                            next_day_str = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
                            
                            if tomorrow_str in start_time or next_day_str in start_time:
                                is_tomorrow = True
                                _LOGGER.debug(f"Identified as tomorrow based on string pattern: {start_time}")
                        
                        if is_tomorrow:
                            tomorrow_hourly_prices[hour_key] = price_val
                            _LOGGER.debug(f"Added TOMORROW price with ISO timestamp: {hour_key} = {raw_price}")
                        else:
                            today_hourly_prices[hour_key] = price_val
                            _LOGGER.debug(f"Added TODAY price with ISO timestamp: {hour_key} = {raw_price}")
                
            # If we found tomorrow's prices, add them to the result
            if tomorrow_hourly_prices:
                result = {
                    "today_hourly_prices": today_hourly_prices,
                    "tomorrow_hourly_prices": tomorrow_hourly_prices
                }
                _LOGGER.info(f"Extracted {len(tomorrow_hourly_prices)} tomorrow prices from unified data format")
                return result
                
            return today_hourly_prices
            
        # Handle "today" data in the old format structure for backward compatibility
        if "today" in data and data["today"]:
            today_data = data["today"]

            if "multiAreaEntries" in today_data:
                for entry in today_data["multiAreaEntries"]:
                    if not isinstance(entry, dict) or "entryPerArea" not in entry:
                        continue

                    if area not in entry["entryPerArea"]:
                        continue

                    # Extract values
                    start_time = entry.get("deliveryStart")
                    raw_price = entry["entryPerArea"][area]

                    if start_time and raw_price is not None:
                        # Parse timestamp
                        dt = self._parse_timestamp(start_time)
                        if dt:
                            # ALWAYS format as ISO format with full date and time using standardized method
                            hour_key = super().format_timestamp_to_iso(dt)
                            price_val = float(raw_price)
                            
                            # Check if this timestamp belongs to tomorrow
                            if super().is_tomorrow_timestamp(dt):
                                tomorrow_hourly_prices[hour_key] = price_val
                                _LOGGER.debug(f"Added TOMORROW price with ISO timestamp: {hour_key} = {raw_price}")
                            else:
                                today_hourly_prices[hour_key] = price_val
                                _LOGGER.debug(f"Added TODAY price with ISO timestamp: {hour_key} = {raw_price}")

        # If we found tomorrow's prices, add them to the result
        if tomorrow_hourly_prices:
            result = {
                "today_hourly_prices": today_hourly_prices,
                "tomorrow_hourly_prices": tomorrow_hourly_prices
            }
            _LOGGER.info(f"Extracted {len(tomorrow_hourly_prices)} tomorrow prices from today data format")
            return result
            
        return today_hourly_prices

    def _extract_prices_from_data(self, data: Dict[str, Any], area: str) -> Dict[str, float]:
        """Extract price data from Nordpool response.
        
        This helper extracts prices from either today or tomorrow data.
        
        Args:
            data: Raw API data segment (today or tomorrow section)
            area: Area code
            
        Returns:
            Dictionary of hourly prices with ISO timestamps as keys
        """
        hourly_prices = {}
        
        if not isinstance(data, dict) or "multiAreaEntries" not in data:
            return hourly_prices
            
        entries = data.get("multiAreaEntries", [])
        
        for entry in entries:
            if not isinstance(entry, dict) or "entryPerArea" not in entry:
                continue

            if area not in entry["entryPerArea"]:
                continue

            # Extract values
            start_time = entry.get("deliveryStart")
            raw_price = entry["entryPerArea"][area]

            if start_time and raw_price is not None:
                # Parse timestamp
                dt = self._parse_timestamp(start_time)
                if dt:
                    # Always format as ISO format with full date and time using standardized method
                    hour_key = super().format_timestamp_to_iso(dt)
                    price_val = float(raw_price)
                    hourly_prices[hour_key] = price_val
                    _LOGGER.debug(f"Extracted price: {hour_key} = {price_val}")
                    
        return hourly_prices
