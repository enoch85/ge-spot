"""Parser for Energi Data Service API responses."""
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from ...const.sources import Source
from ...utils.validation import validate_data
from ...timezone.timezone_utils import normalize_hour_value
from ..base.price_parser import BasePriceParser

_LOGGER = logging.getLogger(__name__)

class EnergiDataParser(BasePriceParser):
    """Parser for Energi Data Service API responses (refactored: returns only raw, unprocessed data)."""

    def __init__(self):
        super().__init__(Source.ENERGI_DATA_SERVICE)

    def parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Energi Data Service API response to raw hourly prices (ISO hour -> price)."""
        data = validate_data(data, self.source)
        result = {"hourly_prices": {}, "currency": data.get("currency", "DKK"), "source": self.source}
        if "hourly_prices" in data and isinstance(data["hourly_prices"], dict):
            result["hourly_prices"] = data["hourly_prices"]
        elif "records" in data and isinstance(data["records"], list):
            for record in data["records"]:
                if "HourDK" in record and "SpotPriceDKK" in record:
                    try:
                        timestamp = self._parse_timestamp(record["HourDK"])
                        if timestamp:
                            hour_key = timestamp.strftime("%Y-%m-%dT%H:00:00")
                            price = float(record["SpotPriceDKK"])
                            result["hourly_prices"][hour_key] = price
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning(f"Failed to parse record: {e}")
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
