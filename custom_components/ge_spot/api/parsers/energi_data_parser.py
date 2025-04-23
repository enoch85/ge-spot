"""Parser for Energi Data Service API responses."""
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from ...const.sources import Source
from ...const.currencies import Currency
from ...utils.validation import validate_data
from ...timezone.timezone_utils import normalize_hour_value
from ..base.price_parser import BasePriceParser

_LOGGER = logging.getLogger(__name__)

class EnergiDataParser(BasePriceParser):
    """Parser for Energi Data Service API responses."""

    def __init__(self, timezone_service=None):
        """Initialize the parser."""
        super().__init__(Source.ENERGI_DATA_SERVICE, timezone_service)

    def parse(self, raw_data: Any) -> Dict[str, Any]:
        """Parse Energi Data Service API response.

        Args:
            raw_data: Raw API response data

        Returns:
            Parsed data with hourly prices
        """
        result = {
            "hourly_prices": {},
            "currency": Currency.DKK
        }

        # Check for valid data
        if not raw_data:
            _LOGGER.warning("Empty Energi Data Service data received")
            return result

        # Extract records from response
        records = None
        if isinstance(raw_data, dict) and "records" in raw_data:
            records = raw_data["records"]
        
        if not records or not isinstance(records, list):
            _LOGGER.warning("No valid records found in Energi Data Service data")
            return result

        # Parse hourly prices from records
        for record in records:
            try:
                # Extract timestamp and price
                if "HourDK" in record and "SpotPriceDKK" in record:
                    # Parse timestamp
                    timestamp_str = record["HourDK"]
                    dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    hour_key = dt.isoformat()
                    
                    # Parse price
                    price = float(record["SpotPriceDKK"])
                    
                    # Add to hourly prices
                    result["hourly_prices"][hour_key] = price
            except (ValueError, TypeError) as e:
                _LOGGER.debug(f"Failed to parse Energi Data Service record: {e}")

        # Calculate current and next hour prices
        result["current_price"] = self._get_current_price(result["hourly_prices"])
        result["next_hour_price"] = self._get_next_hour_price(result["hourly_prices"])

        return result

    def extract_metadata(self, data: Any) -> Dict[str, Any]:
        """Extract metadata from Energi Data Service API response.

        Args:
            data: Raw API response data

        Returns:
            Metadata dictionary
        """
        metadata = super().extract_metadata(data)
        metadata.update({
            "currency": Currency.DKK,  # Default currency for Energi Data Service
            "timezone": "Europe/Copenhagen",
            "area": "DK1",  # Default area
        })

        # Extract additional metadata
        if isinstance(data, dict):
            # Check for area information
            if "area" in data:
                metadata["area"] = data["area"]
            
            # Check for records information
            if "records" in data and isinstance(data["records"], list):
                metadata["record_count"] = len(data["records"])
                
                # Extract area from the first record if available
                if data["records"] and "PriceArea" in data["records"][0]:
                    metadata["area"] = data["records"][0]["PriceArea"]

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
