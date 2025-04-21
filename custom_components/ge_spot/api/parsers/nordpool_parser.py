"""Parser for Nordpool API responses."""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from ...const.sources import Source
from ...utils.validation import validate_data
from ..base.price_parser import BasePriceParser

_LOGGER = logging.getLogger(__name__)

class NordpoolPriceParser(BasePriceParser):
    """Parser for Nordpool API responses.
    
    This parser only extracts raw data from the API response without any processing.
    Processing is handled by the data managers.
    """

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

        # Extract raw data from the response
        raw_data = data.get("raw_data", data)

        # Create a result dictionary with basic metadata
        result = {
            "source": self.source,
            "currency": "EUR",  # Nordpool API returns prices in EUR
            "market_type": data.get("market_type", "DayAhead"),
            "raw_data": raw_data
        }

        # Extract today and tomorrow data if available in the combined format
        if isinstance(raw_data, dict) and "today" in raw_data and "tomorrow" in raw_data:
            result["today_data"] = raw_data["today"]
            result["tomorrow_data"] = raw_data["tomorrow"]
        else:
            # If not in combined format, use the raw data as today's data
            result["today_data"] = raw_data

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
            "market_type": data.get("market_type", "DayAhead")
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

    def extract_prices(self, data: Dict[str, Any], area: str) -> Dict[str, Any]:
        """Extract raw price data from Nordpool response.

        Args:
            data: Raw API response data
            area: Area code

        Returns:
            Dictionary with raw price data
        """
        result = {
            "today_entries": [],
            "tomorrow_entries": []
        }

        # Extract today's data
        today_data = data.get("today_data", data)
        if isinstance(today_data, dict) and "multiAreaEntries" in today_data:
            for entry in today_data["multiAreaEntries"]:
                if not isinstance(entry, dict) or "entryPerArea" not in entry:
                    continue

                if area not in entry["entryPerArea"]:
                    continue

                # Extract values
                start_time = entry.get("deliveryStart")
                end_time = entry.get("deliveryEnd")
                raw_price = entry["entryPerArea"][area]

                if start_time and raw_price is not None:
                    # Add to today entries
                    result["today_entries"].append({
                        "start": start_time,
                        "end": end_time,
                        "price": raw_price
                    })

        # Extract tomorrow's data
        tomorrow_data = data.get("tomorrow_data")
        if isinstance(tomorrow_data, dict) and "multiAreaEntries" in tomorrow_data:
            for entry in tomorrow_data["multiAreaEntries"]:
                if not isinstance(entry, dict) or "entryPerArea" not in entry:
                    continue

                if area not in entry["entryPerArea"]:
                    continue

                # Extract values
                start_time = entry.get("deliveryStart")
                end_time = entry.get("deliveryEnd")
                raw_price = entry["entryPerArea"][area]

                if start_time and raw_price is not None:
                    # Add to tomorrow entries
                    result["tomorrow_entries"].append({
                        "start": start_time,
                        "end": end_time,
                        "price": raw_price
                    })

        return result
