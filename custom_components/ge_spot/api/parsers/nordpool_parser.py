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
            "source": self.source,
            "market_type": data.get("market_type")  # Store market type similar to ENTSOE's document type
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

    def extract_metadata(self, data: Any) -> Dict[str, Any]:
        """Extract metadata from Nordpool API response.

        Args:
            data: Raw API response data

        Returns:
            Metadata dictionary
        """
        metadata = {
            "currency": "EUR",  # Default currency for Nordpool
            "market_type": data.get("market_type", "DayAhead")  # Similar to ENTSOE's document type
        }

        # If data is a dictionary, try to extract currency
        if isinstance(data, dict):
            if "currency" in data:
                metadata["currency"] = data["currency"]
            
            # Extract market type if available
            if "market_type" in data:
                metadata["market_type"] = data["market_type"]
            elif "market" in data:
                metadata["market_type"] = data["market"]

        return metadata

    def _select_best_time_series(self, all_series: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Select the best TimeSeries to use for price data.

        Args:
            all_series: List of dictionaries with metadata and prices

        Returns:
            The best TimeSeries or None if no valid series found
        """
        if not all_series:
            return None

        # If only one series, use it
        if len(all_series) == 1:
            return all_series[0]

        # Get current date in UTC
        today = datetime.now(timezone.utc).date()

        # Filter series that contain today's data
        today_series = []
        for series in all_series:
            # Extract hour keys
            hour_keys = list(series["prices"].keys())
            if not hour_keys:
                continue

            # Try to find a price entry for today
            for hour_key in hour_keys:
                try:
                    hour_dt = datetime.fromisoformat(hour_key)
                    if hour_dt.date() == today:
                        today_series.append(series)
                        break
                except (ValueError, TypeError):
                    continue

        # If we found series containing today's data, use those
        if today_series:
            _LOGGER.debug(f"Found {len(today_series)} TimeSeries containing today's data")

            # If only one series contains today's data, use it
            if len(today_series) == 1:
                _LOGGER.debug("Using the only TimeSeries that contains today's data")
                return today_series[0]

            # If multiple series contain today's data, use market type criteria
            for series in today_series:
                if series["metadata"]["market_type"] == "DayAhead":
                    _LOGGER.debug("Selected TimeSeries with market_type DayAhead containing today's data")
                    return series

            # Fall back to first series containing today's data
            _LOGGER.debug("Falling back to first TimeSeries containing today's data")
            return today_series[0]

        _LOGGER.debug("No TimeSeries contains today's data, falling back to market type criteria")

        # If no series contains today's data, fall back to market type criteria
        # First try to identify by market type
        for series in all_series:
            if series["metadata"]["market_type"] == "DayAhead":
                return series

        # Fallback: try a heuristic approach
        # Use overnight prices as a heuristic (should be lower)
        overnight_averages = []
        for series in all_series:
            overnight_prices = []
            for hour_str, price in series["prices"].items():
                try:
                    hour_dt = datetime.fromisoformat(hour_str)
                    hour = hour_dt.hour
                    if 0 <= hour <= 6:  # Overnight hours
                        overnight_prices.append(price)
                except (ValueError, TypeError):
                    # Try simple hour format
                    try:
                        hour = int(hour_str.split(":")[0])
                        if 0 <= hour <= 6:  # Overnight hours
                            overnight_prices.append(price)
                    except (ValueError, TypeError, IndexError):
                        continue

            if overnight_prices:
                avg = sum(overnight_prices) / len(overnight_prices)
                overnight_averages.append({
                    "series": series,
                    "overnight_avg": avg
                })

        # Choose the series with the lowest overnight average
        if overnight_averages:
            overnight_averages.sort(key=lambda x: x["overnight_avg"])
            return overnight_averages[0]["series"]

        # If all else fails, use the first series
        return all_series[0]

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

    def parse_hourly_prices(self, data: Dict[str, Any], area: str) -> Dict[str, Any]:
        """Parse hourly prices from Nordpool data.

        Args:
            data: Raw API response data
            area: Area code

        Returns:
            Dictionary of hourly prices with ISO format timestamp keys or
            a dictionary with both 'today_hourly_prices' and 'tomorrow_hourly_prices'
        """
        # Extract all hourly prices with their ISO timestamps
        # We'll return them in the format expected by the API
        hourly_prices = {}
        
        # We'll also keep track of tomorrow's prices separately
        # This is needed for the API to work correctly
        tomorrow_hourly_prices = self.parse_tomorrow_prices(data, area)

        # Store all time series for selection - similar to ENTSOE approach
        all_time_series = []

        # Handle the combined format with today and tomorrow data
        if "today" in data and data["tomorrow"]:
            # Process today's data
            if "multiAreaEntries" in data["today"]:
                today_prices = self._extract_prices_from_data(data["today"], area)
                
                # Add to all time series for selection
                all_time_series.append({
                    "metadata": {
                        "market_type": data.get("market_type", "DayAhead"),
                        "source": "today"
                    },
                    "prices": today_prices
                })
                
                # Merge prices
                hourly_prices.update(today_prices)
            
            # Process tomorrow's data
            if "tomorrow" in data and data["tomorrow"] and "multiAreaEntries" in data["tomorrow"]:
                tomorrow_prices = self._extract_prices_from_data(data["tomorrow"], area)
                
                # Add to all time series for selection
                all_time_series.append({
                    "metadata": {
                        "market_type": data.get("market_type", "DayAhead"),
                        "source": "tomorrow"
                    },
                    "prices": tomorrow_prices
                })
                
                # Update tomorrow hourly prices
                tomorrow_hourly_prices.update(tomorrow_prices)
        
        # Similar approach to ENTSOE - handle the data directly
        elif "data" in data and isinstance(data["data"], dict):
            # Process the data using the provided structure
            api_data = data["data"]

            # Check if we have multiAreaEntries in the response
            if "multiAreaEntries" in api_data:
                data_prices = self._extract_prices_from_data(api_data, area)
                
                # Add to all time series for selection
                all_time_series.append({
                    "metadata": {
                        "market_type": data.get("market_type", "DayAhead"),
                        "source": "data"
                    },
                    "prices": data_prices
                })
                
                # Merge prices
                hourly_prices.update(data_prices)

        # Alternative: Handle raw multiAreaEntries at top level
        elif "multiAreaEntries" in data:
            raw_prices = self._extract_prices_from_data(data, area)
            
            # Add to all time series for selection
            all_time_series.append({
                "metadata": {
                    "market_type": data.get("market_type", "DayAhead"),
                    "source": "raw"
                },
                "prices": raw_prices
            })
            
            # Merge prices
            hourly_prices.update(raw_prices)

        # Select the best time series if we have multiple - similar to ENTSOE
        if len(all_time_series) > 1:
            best_series = self._select_best_time_series(all_time_series)
            if best_series:
                _LOGGER.debug(f"Selected best time series from source: {best_series['metadata']['source']}")
                # We don't replace hourly_prices here because we want to keep all data
                # This is different from ENTSOE which selects only one time series
        
        # For Nordpool, we need to keep all the data in today_hourly_prices
        # This is because the API is designed to work with today's data
        today_hourly_prices = {}
        tomorrow_hourly_prices_final = {}
        
        # Get today's date for comparison
        today = datetime.now(timezone.utc).date()
        tomorrow = today + timedelta(days=1)
        
        # First, convert all ISO timestamps to HH:00 format
        for hour_key, price in hourly_prices.items():
            try:
                if "T" in hour_key:  # ISO format
                    dt = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
                    # Convert to HH:00 format
                    simple_key = f"{dt.hour:02d}:00"
                    
                    # For Nordpool, we keep all data in today_hourly_prices
                    today_hourly_prices[simple_key] = price
            except (ValueError, TypeError):
                # Keep the original key if we can't parse it
                _LOGGER.debug(f"Could not parse date from hour key: {hour_key}")
                today_hourly_prices[hour_key] = price
        
        # Now handle tomorrow's data separately
        # This data comes from the separate tomorrow data extraction
        for hour_key, price in tomorrow_hourly_prices.items():
            try:
                if "T" in hour_key:  # ISO format
                    dt = datetime.fromisoformat(hour_key.replace('Z', '+00:00'))
                    # Convert to HH:00 format
                    simple_key = f"{dt.hour:02d}:00"
                    tomorrow_hourly_prices_final[simple_key] = price
            except (ValueError, TypeError):
                # Keep the original key if we can't parse it
                tomorrow_hourly_prices_final[hour_key] = price
        
        _LOGGER.debug(f"Separated today prices: {len(today_hourly_prices)} entries")
        _LOGGER.debug(f"Separated tomorrow prices: {len(tomorrow_hourly_prices_final)} entries")
        
        # Return hourly prices in the format expected by the API
        return {
            "today_hourly_prices": today_hourly_prices,
            "tomorrow_hourly_prices": tomorrow_hourly_prices_final
        }
        
    def parse_tomorrow_prices(self, data: Dict[str, Any], area: str) -> Dict[str, float]:
        """Parse tomorrow hourly prices from Nordpool data.

        Args:
            data: Raw API response data
            area: Area code

        Returns:
            Dictionary of tomorrow hourly prices with hour string keys (HH:00)
        """
        tomorrow_hourly_prices = {}
        
        # Get tomorrow's date for comparison
        today = datetime.now(timezone.utc).date()
        tomorrow = today + timedelta(days=1)
        
        # Handle "tomorrow" data in the structure
        if "tomorrow" in data and data["tomorrow"]:
            tomorrow_data = data["tomorrow"]
            
            if isinstance(tomorrow_data, dict) and "multiAreaEntries" in tomorrow_data:
                _LOGGER.debug(f"Processing {len(tomorrow_data['multiAreaEntries'])} entries from tomorrow data")
                
                for entry in tomorrow_data["multiAreaEntries"]:
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
                            # Format as ISO format with full date and time
                            hour_key = super().format_timestamp_to_iso(dt)
                            price_val = float(raw_price)
                            
                            # Store the price with the ISO timestamp
                            tomorrow_hourly_prices[hour_key] = price_val
                            _LOGGER.debug(f"Extracted price from tomorrow data: {hour_key} = {raw_price}")
                            
                            # Also store in simple HH:00 format for direct use
                            simple_key = f"{dt.hour:02d}:00"
                            tomorrow_hourly_prices[simple_key] = price_val
                            
                            # Always consider entries from tomorrow_data as tomorrow's data
                            # regardless of the actual date in the timestamp
                            _LOGGER.debug(f"Adding tomorrow price: {simple_key} = {price_val}")
        
        # Also check for tomorrow's data in the combined response
        # This is needed for the direct API test which fetches tomorrow's data separately
        if "today" in data and isinstance(data["today"], dict) and "multiAreaEntries" in data["today"]:
            # Process entries from today's data that might be for tomorrow
            for entry in data["today"]["multiAreaEntries"]:
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
                    if dt and dt.date() == tomorrow:
                        # This entry is for tomorrow
                        hour_key = super().format_timestamp_to_iso(dt)
                        price_val = float(raw_price)
                        
                        # Store the price with the ISO timestamp
                        tomorrow_hourly_prices[hour_key] = price_val
                        _LOGGER.debug(f"Extracted tomorrow price from today data: {hour_key} = {raw_price}")
        
        return tomorrow_hourly_prices

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
