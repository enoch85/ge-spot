"""Parser for Stromligning API responses."""
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from ...const.sources import Source
from ...timezone.timezone_utils import normalize_hour_value
from ...utils.validation import validate_data
from ..base.price_parser import BasePriceParser

_LOGGER = logging.getLogger(__name__)

class StromligningParser(BasePriceParser):
    """Parser for Stromligning API responses."""

    def __init__(self):
        """Initialize the parser."""
        super().__init__(Source.STROMLIGNING)
        self._price_components = {}

    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Stromligning API response.

        Args:
            data: Raw API response data

        Returns:
            Parsed data with hourly prices
        """
        # Validate data
        data = validate_data(data, self.source)

        result = {
            "hourly_prices": {},
            "currency": data.get("currency", "DKK"),
            "source": self.source
        }

        # If hourly prices were already processed
        if "hourly_prices" in data and isinstance(data["hourly_prices"], dict):
            result["hourly_prices"] = data["hourly_prices"]
        elif "prices" in data and isinstance(data["prices"], list):
            # Parse prices from Stromligning
            for price_data in data["prices"]:
                if "date" in price_data and "price" in price_data and "value" in price_data["price"]:
                    try:
                        # Parse timestamp
                        timestamp = self._parse_timestamp(price_data["date"])
                        if timestamp:
                            # Format as ISO string for the hour
                            hour_key = timestamp.strftime("%Y-%m-%dT%H:00:00")

                            # Parse price
                            price = float(price_data["price"]["value"])

                            # Add to hourly prices
                            result["hourly_prices"][hour_key] = price

                            # Extract price components if available
                            if "components" in price_data["price"] and isinstance(price_data["price"]["components"], list):
                                hour_str = f"{timestamp.hour:02d}:00"
                                self._price_components[hour_str] = {}

                                for component in price_data["price"]["components"]:
                                    if "name" in component and "value" in component:
                                        component_name = component["name"]
                                        component_value = float(component["value"])
                                        self._price_components[hour_str][component_name] = component_value
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse Stromligning price: {e}")
        elif "raw_data" in data and isinstance(data["raw_data"], str):
            # Try to parse raw data as JSON
            try:
                json_data = json.loads(data["raw_data"])

                # Check if it's the expected format
                if "prices" in json_data and isinstance(json_data["prices"], list):
                    for price_data in json_data["prices"]:
                        if "date" in price_data and "price" in price_data and "value" in price_data["price"]:
                            try:
                                # Parse timestamp
                                timestamp = self._parse_timestamp(price_data["date"])
                                if timestamp:
                                    # Format as ISO string for the hour
                                    hour_key = timestamp.strftime("%Y-%m-%dT%H:00:00")

                                    # Parse price
                                    price = float(price_data["price"]["value"])

                                    # Add to hourly prices
                                    result["hourly_prices"][hour_key] = price

                                    # Extract price components if available
                                    if "components" in price_data["price"] and isinstance(price_data["price"]["components"], list):
                                        hour_str = f"{timestamp.hour:02d}:00"
                                        self._price_components[hour_str] = {}

                                        for component in price_data["price"]["components"]:
                                            if "name" in component and "value" in component:
                                                component_name = component["name"]
                                                component_value = float(component["value"])
                                                self._price_components[hour_str][component_name] = component_value
                            except (ValueError, TypeError) as e:
                                _LOGGER.warning(f"Failed to parse Stromligning price from JSON: {e}")
            except json.JSONDecodeError as e:
                _LOGGER.warning(f"Failed to parse Stromligning raw data as JSON: {e}")

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

    def extract_metadata(self, data: Any) -> Dict[str, Any]:
        """Extract metadata from Stromligning API response.

        Args:
            data: Raw API response data

        Returns:
            Metadata dictionary
        """
        metadata = {
            "currency": "DKK",  # Default currency for Stromligning
        }

        # Extract price area if available
        if isinstance(data, dict) and "priceArea" in data:
            metadata["price_area"] = data["priceArea"]

        # Check if we have price components
        has_components = False
        component_types = set()

        if isinstance(data, dict) and "prices" in data and isinstance(data["prices"], list):
            for price_data in data["prices"]:
                if "price" in price_data and "components" in price_data["price"] and isinstance(price_data["price"]["components"], list):
                    has_components = True

                    # Extract component types
                    for component in price_data["price"]["components"]:
                        if "name" in component:
                            component_types.add(component["name"])

        metadata["has_components"] = has_components
        if component_types:
            metadata["component_types"] = list(component_types)

        return metadata

    def parse_hourly_prices(self, data: Any, area: str) -> Dict[str, float]:
        """Parse hourly prices from Stromligning API response.

        Args:
            data: Raw API response data
            area: Area code

        Returns:
            Dictionary of hourly prices with hour string keys (HH:00)
        """
        hourly_prices = {}

        if isinstance(data, dict) and "prices" in data and isinstance(data["prices"], list):
            for price_data in data["prices"]:
                if "date" in price_data and "price" in price_data and "value" in price_data["price"]:
                    try:
                        # Parse timestamp
                        timestamp = self._parse_timestamp(price_data["date"])
                        if timestamp:
                            # Format as hour string (HH:00)
                            normalized_hour, adjusted_date = normalize_hour_value(timestamp.hour, timestamp.date())
                            hour_key = f"{normalized_hour:02d}:00"

                            # Parse price
                            price = float(price_data["price"]["value"])

                            # Add to hourly prices
                            hourly_prices[hour_key] = price

                            # Extract price components if available
                            if "components" in price_data["price"] and isinstance(price_data["price"]["components"], list):
                                self._price_components[hour_key] = {}

                                for component in price_data["price"]["components"]:
                                    if "name" in component and "value" in component:
                                        component_name = component["name"]
                                        component_value = float(component["value"])
                                        self._price_components[hour_key][component_name] = component_value
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse Stromligning price: {e}")

        return hourly_prices

    def get_price_components(self) -> Dict[str, Dict[str, float]]:
        """Get price components.

        Returns:
            Dictionary of price components by hour
        """
        return self._price_components

    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse timestamp from Stromligning format.

        Args:
            timestamp_str: Timestamp string

        Returns:
            Parsed datetime or None if parsing fails
        """
        try:
            # Stromligning typically uses ISO format
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            # Try common formats
            formats = [
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d"
            ]

            for fmt in formats:
                try:
                    dt = datetime.strptime(timestamp_str, fmt)

                    # If only date is provided, assume start of day
                    if fmt == "%Y-%m-%d":
                        return dt

                    return dt
                except ValueError:
                    continue

            _LOGGER.warning(f"Failed to parse timestamp: {timestamp_str}")
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
