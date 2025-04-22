"""Parser for Stromligning API."""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple

from ...const.api import SourceTimezone
from ...const.sources import Source
from ...const.currencies import Currency
from ...utils.price_extractor import ensure_iso_timestamp

_LOGGER = logging.getLogger(__name__)

class StromligningParser:
    """Parser for Stromligning API."""

    def __init__(self, area: str):
        """Initialize the parser.
        
        Args:
            area: Area code
        """
        self.area = area
        
    def parse_prices(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse prices from Stromligning API response.
        
        Args:
            data: API response
            
        Returns:
            Dictionary with parsed prices
        """
        result = {
            "hourly_prices": {},
            "currency": Currency.DKK,
            "api_timezone": SourceTimezone.API_TIMEZONES[Source.STROMLIGNING],
            "raw_data": data,
        }
        
        # Extract raw data
        raw_data = data
        if "raw_data" in data:
            raw_data = data["raw_data"]
        
        # Check if we have nested raw_data
        if "raw_data" in raw_data:
            raw_data = raw_data["raw_data"]
        
        # Extract prices from the prices array
        if "prices" in raw_data and isinstance(raw_data["prices"], list):
            prices = raw_data["prices"]
            for price_entry in prices:
                if isinstance(price_entry, dict) and "date" in price_entry and "price" in price_entry:
                    try:
                        timestamp_str = price_entry["date"]
                        price_obj = price_entry["price"]
                        
                        # Extract the price value
                        price_value = None
                        if isinstance(price_obj, dict):
                            if "value" in price_obj:
                                price_value = price_obj["value"]
                            elif "total" in price_obj:
                                price_value = price_obj["total"]
                        
                        # Convert to float if it's a string or number
                        if isinstance(price_value, (int, float, str)):
                            price_value = float(price_value)
                            # Ensure timestamp is in ISO format
                            iso_timestamp = ensure_iso_timestamp(timestamp_str)
                            result["hourly_prices"][iso_timestamp] = price_value
                            _LOGGER.debug(f"Successfully extracted price {price_value} for timestamp {iso_timestamp}")
                    except (ValueError, TypeError) as e:
                        _LOGGER.debug(f"Failed to parse Stromligning price entry: {price_entry} - {e}")
        
        return result
