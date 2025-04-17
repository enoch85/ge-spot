"""Parser for Nordpool API responses."""
import logging
from datetime import datetime, timedelta
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
            "hourly_prices": {},
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
                                result["hourly_prices"][hour_key] = price

                    # Only process the first area with prices
                    if result["hourly_prices"]:
                        break

        # If hourly prices were already processed
        if "hourly_prices" in data and isinstance(data["hourly_prices"], dict):
            result["hourly_prices"] = data["hourly_prices"]

        # Add current and next hour prices if available
        if "current_price" in data:
            result["current_price"] = data["current_price"]

        if "next_hour_price" in data:
            result["next_hour_price"] = data["next_hour_price"]

        # Calculate current and next hour prices if not provided
        if "current_price" not in result:
            result["current_price"] = self._get_current_price(result["hourly_prices"])

        if "next_hour_price" not in result:
            result["next_hour_price"] = self._get_next_hour_price(result["hourly_prices"])

        # Calculate day average if enough prices
        if len(result["hourly_prices"]) >= 12:
            result["day_average_price"] = self._calculate_day_average(result["hourly_prices"])

        return result

    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse timestamp from Nordpool format.

        Args:
            timestamp_str: Timestamp string

        Returns:
            Parsed datetime or None if parsing fails
        """
        try:
            # Try ISO format
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            try:
                # Try Nordpool specific format
                return datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%f")
            except (ValueError, AttributeError):
                _LOGGER.warning(f"Failed to parse timestamp: {timestamp_str}")
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

        now = datetime.now()
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        current_hour_key = current_hour.strftime("%Y-%m-%dT%H:00:00")

        return hourly_prices.get(current_hour_key)

    def _get_next_hour_price(self, hourly_prices: Dict[str, float]) -> Optional[float]:
        """Get next hour price.

        Args:
            hourly_prices: Dictionary of hourly prices

        Returns:
            Next hour price or None if not available
        """
        if not hourly_prices:
            return None

        now = datetime.now()
        next_hour = (now.replace(minute=0, second=0, microsecond=0) +
                    timedelta(hours=1))
        next_hour_key = next_hour.strftime("%Y-%m-%dT%H:00:00")

        return hourly_prices.get(next_hour_key)

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
        today = datetime.now().date()

        # Filter prices for today
        today_prices = []
        for hour_key, price in hourly_prices.items():
            try:
                hour_dt = datetime.fromisoformat(hour_key)
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
            Dictionary of hourly prices
        """
        hourly_prices = {}

        # Process today's data
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
                            # Format as hour key
                            normalized_hour, adjusted_date = normalize_hour_value(dt.hour, dt.date())
                            hour_key = f"{normalized_hour:02d}:00"
                            hourly_prices[hour_key] = float(raw_price)

        return hourly_prices

    def parse_tomorrow_prices(self, data: Dict[str, Any], area: str) -> Dict[str, float]:
        """Parse tomorrow's hourly prices from Nordpool data.

        Args:
            data: Raw API response data
            area: Area code

        Returns:
            Dictionary of hourly prices
        """
        hourly_prices = {}

        # Process tomorrow's data
        if "tomorrow" in data and data["tomorrow"]:
            tomorrow_data = data["tomorrow"]

            if "multiAreaEntries" in tomorrow_data:
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
                            # Format as hour key
                            normalized_hour, adjusted_date = normalize_hour_value(dt.hour, dt.date())
                            hour_key = f"{normalized_hour:02d}:00"
                            hourly_prices[hour_key] = float(raw_price)

        return hourly_prices
