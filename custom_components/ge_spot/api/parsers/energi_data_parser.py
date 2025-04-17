"""Parser for Energi Data Service API responses."""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from ...const.sources import Source
from ...timezone.timezone_utils import normalize_hour_value
from ...utils.validation import validate_data
from ..base.price_parser import BasePriceParser

_LOGGER = logging.getLogger(__name__)

class EnergiDataParser(BasePriceParser):
    """Parser for Energi Data Service API responses."""

    def __init__(self):
        """Initialize the parser."""
        super().__init__(Source.ENERGI_DATA_SERVICE)

    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Energi Data Service API response.

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
        elif "records" in data and isinstance(data["records"], list):
            # Parse records from Energi Data Service
            for record in data["records"]:
                if "HourDK" in record and "SpotPriceDKK" in record:
                    try:
                        # Parse timestamp
                        timestamp = self._parse_timestamp(record["HourDK"])
                        if timestamp:
                            # Format as ISO string for the hour
                            hour_key = timestamp.strftime("%Y-%m-%dT%H:00:00")

                            # Parse price
                            price = float(record["SpotPriceDKK"])

                            # Add to hourly prices
                            result["hourly_prices"][hour_key] = price
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse record: {e}")

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

    def extract_metadata(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metadata from Energi Data Service API response.

        Args:
            data: Raw API response data

        Returns:
            Metadata dictionary
        """
        metadata = {
            "currency": "DKK",  # Default currency for Energi Data Service
            "has_eur_prices": False
        }

        # Check if we have records
        if "records" in data and isinstance(data["records"], list) and data["records"]:
            # Get first record for metadata
            first_record = data["records"][0]

            # Check for area
            if "PriceArea" in first_record:
                metadata["area"] = first_record["PriceArea"]

            # Check for dataset info
            if "dataset" in data:
                metadata["dataset"] = data["dataset"]

            # Check if EUR prices are available
            if "SpotPriceEUR" in first_record:
                metadata["has_eur_prices"] = True

        return metadata

    def parse_hourly_prices(self, data: Dict[str, Any], area: str) -> Dict[str, float]:
        """Parse hourly prices from Energi Data Service API response.

        Args:
            data: Raw API response data
            area: Area code

        Returns:
            Dictionary of hourly prices with hour string keys (HH:00)
        """
        hourly_prices = {}

        # Check if we have records
        if "records" in data and isinstance(data["records"], list):
            for record in data["records"]:
                if "HourDK" in record and "SpotPriceDKK" in record:
                    try:
                        # Parse timestamp
                        timestamp = self._parse_timestamp(record["HourDK"])
                        if timestamp:
                            # Format as hour string (HH:00)
                            normalized_hour, adjusted_date = normalize_hour_value(timestamp.hour, timestamp.date())
                            hour_key = f"{normalized_hour:02d}:00"

                            # Parse price
                            price = float(record["SpotPriceDKK"])

                            # Add to hourly prices
                            hourly_prices[hour_key] = price
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse record: {e}")

        return hourly_prices

    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parse timestamp from Energi Data Service format.

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
                # Try Energi Data Service specific format (YYYY-MM-DD HH:MM)
                return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
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
